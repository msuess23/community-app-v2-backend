"""Lifecycle command tests without requiring a running PostgreSQL database."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.appointment.domain import AppointmentEventType, AppointmentSlotStatus, AppointmentStatus
from src.appointment.event_store import AppointmentEventStore
from src.appointment.lifecycle_service import AppointmentLifecycleService
from src.appointment.models import Appointment, AppointmentSlot
from src.appointment.repository import AppointmentRepository, AppointmentSlotRepository
from src.appointment.schemas import (
  AppointmentCancelRequest,
  AppointmentCompleteRequest,
  AppointmentRescheduleRequest,
)
from src.user.models import Role, User


def _user(role: Role, *, office_id=None, user_id=None) -> User:
  return User(
    id=user_id or uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="hash",
    first_name="Appointment",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _appointment(citizen_id, office_id, slot_id, *, starts_at) -> Appointment:
  return Appointment(
    id=uuid.uuid4(),
    current_slot_id=slot_id,
    office_id=office_id,
    citizen_id=citizen_id,
    status=AppointmentStatus.SCHEDULED,
    starts_at=starts_at,
    ends_at=starts_at + timedelta(minutes=30),
    version=1,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
  )


def _db() -> MagicMock:
  db = MagicMock()
  db.flush = AsyncMock()
  return db


@pytest.mark.asyncio
async def test_reschedule_releases_old_slot_and_books_target(monkeypatch) -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  old_id, target_id = uuid.uuid4(), uuid.uuid4()
  starts = datetime.now(timezone.utc) + timedelta(days=2)
  appointment = _appointment(citizen.id, office_id, old_id, starts_at=starts)
  old_slot = AppointmentSlot(
    id=old_id,
    office_id=office_id,
    starts_at=starts,
    ends_at=starts + timedelta(minutes=30),
    status=AppointmentSlotStatus.BOOKED,
    created_by_user_id=uuid.uuid4(),
  )
  target_slot = AppointmentSlot(
    id=target_id,
    office_id=office_id,
    starts_at=starts + timedelta(days=1),
    ends_at=starts + timedelta(days=1, minutes=30),
    status=AppointmentSlotStatus.AVAILABLE,
    created_by_user_id=uuid.uuid4(),
  )
  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  monkeypatch.setattr(
    AppointmentSlotRepository,
    "get_many_for_update",
    AsyncMock(return_value={old_id: old_slot, target_id: target_slot}),
  )

  async def append(_db, projection, **kwargs):
    assert kwargs["event_type"] == AppointmentEventType.APPOINTMENT_RESCHEDULED
    projection.current_slot_id = target_id
    projection.starts_at = target_slot.starts_at
    projection.ends_at = target_slot.ends_at
    projection.version += 1

  monkeypatch.setattr(AppointmentEventStore, "append", append)
  result = await AppointmentLifecycleService.reschedule(
    _db(),
    appointment_id=appointment.id,
    request=AppointmentRescheduleRequest(
      target_slot_id=target_id,
      reason="Citizen selected another day",
    ),
    current_user=citizen,
  )

  assert old_slot.status == AppointmentSlotStatus.AVAILABLE
  assert target_slot.status == AppointmentSlotStatus.BOOKED
  assert result.current_slot_id == target_id
  assert result.version == 2


@pytest.mark.asyncio
async def test_cancel_releases_the_current_slot(monkeypatch) -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  slot_id = uuid.uuid4()
  starts = datetime.now(timezone.utc) + timedelta(days=2)
  appointment = _appointment(citizen.id, office_id, slot_id, starts_at=starts)
  slot = AppointmentSlot(
    id=slot_id,
    office_id=office_id,
    starts_at=starts,
    ends_at=starts + timedelta(minutes=30),
    status=AppointmentSlotStatus.BOOKED,
    created_by_user_id=uuid.uuid4(),
  )
  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  monkeypatch.setattr(
    AppointmentSlotRepository,
    "get_by_id",
    AsyncMock(return_value=slot),
  )

  async def append(_db, projection, **kwargs):
    assert kwargs["event_type"] == AppointmentEventType.APPOINTMENT_CANCELLED
    projection.current_slot_id = None
    projection.status = AppointmentStatus.CANCELLED
    projection.version += 1

  monkeypatch.setattr(AppointmentEventStore, "append", append)
  result = await AppointmentLifecycleService.cancel(
    _db(),
    appointment_id=appointment.id,
    request=AppointmentCancelRequest(reason="Appointment no longer needed"),
    current_user=citizen,
  )

  assert slot.status == AppointmentSlotStatus.AVAILABLE
  assert result.status == AppointmentStatus.CANCELLED
  assert result.current_slot_id is None


@pytest.mark.asyncio
async def test_complete_consumes_slot_and_requires_responsible_office(monkeypatch) -> None:
  office_id = uuid.uuid4()
  officer = _user(Role.OFFICER, office_id=office_id)
  slot_id = uuid.uuid4()
  starts = datetime.now(timezone.utc) - timedelta(minutes=5)
  appointment = _appointment(uuid.uuid4(), office_id, slot_id, starts_at=starts)
  slot = AppointmentSlot(
    id=slot_id,
    office_id=office_id,
    starts_at=starts,
    ends_at=starts + timedelta(minutes=30),
    status=AppointmentSlotStatus.BOOKED,
    created_by_user_id=uuid.uuid4(),
  )
  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  monkeypatch.setattr(
    AppointmentSlotRepository,
    "get_by_id",
    AsyncMock(return_value=slot),
  )

  async def append(_db, projection, **kwargs):
    assert kwargs["event_type"] == AppointmentEventType.APPOINTMENT_COMPLETED
    projection.status = AppointmentStatus.COMPLETED
    projection.version += 1

  monkeypatch.setattr(AppointmentEventStore, "append", append)
  result = await AppointmentLifecycleService.complete(
    _db(),
    appointment_id=appointment.id,
    request=AppointmentCompleteRequest(comment="Citizen request recorded"),
    current_user=officer,
  )

  assert slot.status == AppointmentSlotStatus.CONSUMED
  assert result.status == AppointmentStatus.COMPLETED
  assert result.allowed_actions == []
