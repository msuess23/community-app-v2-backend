"""Slot creation rules independent of a running PostgreSQL database."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.appointment.schemas import AppointmentSlotBatchCreate
from src.appointment.service import AppointmentSlotService
from src.core.exceptions import DomainValidationException
from src.office.models import Office
from src.user.models import Role, User


def _officer(office_id: uuid.UUID) -> User:
  return User(
    id=uuid.uuid4(),
    email="slot.officer@example.com",
    hashed_password="hash",
    first_name="Slot",
    last_name="Officer",
    role=Role.OFFICER,
    office_id=office_id,
    is_active=True,
  )


@pytest.mark.asyncio
async def test_adjacent_slots_are_allowed(monkeypatch) -> None:
  office_id = uuid.uuid4()
  office = Office(
    id=office_id,
    name="Appointment Office",
    services=[],
    opening_hours={},
    is_active=True,
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentSlotRepository.get_office_for_update",
    AsyncMock(return_value=office),
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentSlotRepository.has_overlap",
    AsyncMock(return_value=False),
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentSlotRepository.add_all",
    lambda db, slots: None,
  )
  db = AsyncMock()
  now = datetime.now(timezone.utc) + timedelta(days=1)
  request = AppointmentSlotBatchCreate(
    slots=[
      {"starts_at": now, "ends_at": now + timedelta(minutes=30)},
      {
        "starts_at": now + timedelta(minutes=30),
        "ends_at": now + timedelta(minutes=60),
      },
    ]
  )

  result = await AppointmentSlotService.create_slots(
    db,
    office_id=office_id,
    request=request,
    current_user=_officer(office_id),
  )

  assert len(result) == 2
  assert result[0].ends_at == result[1].starts_at
  db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_overlapping_input_is_rejected_before_database_write(monkeypatch) -> None:
  office_id = uuid.uuid4()
  office = Office(
    id=office_id,
    name="Appointment Office",
    services=[],
    opening_hours={},
    is_active=True,
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentSlotRepository.get_office_for_update",
    AsyncMock(return_value=office),
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentSlotRepository.has_overlap",
    AsyncMock(return_value=False),
  )
  db = AsyncMock()
  now = datetime.now(timezone.utc) + timedelta(days=1)
  request = AppointmentSlotBatchCreate(
    slots=[
      {"starts_at": now, "ends_at": now + timedelta(minutes=45)},
      {
        "starts_at": now + timedelta(minutes=30),
        "ends_at": now + timedelta(minutes=60),
      },
    ]
  )

  with pytest.raises(DomainValidationException) as exc:
    await AppointmentSlotService.create_slots(
      db,
      office_id=office_id,
      request=request,
      current_user=_officer(office_id),
    )

  assert exc.value.error_code == "APPOINTMENT_SLOT_OVERLAP"
  db.flush.assert_not_awaited()
