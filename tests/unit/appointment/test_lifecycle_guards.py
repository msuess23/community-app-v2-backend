"""Cross-domain lifecycle guards for scheduled appointment commitments."""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.appointment.lifecycle_guard import AppointmentLifecycleGuard
from src.appointment.repository import AppointmentRepository, AppointmentSlotRepository
from src.core.exceptions import ConflictException


@pytest.mark.asyncio
async def test_citizen_with_scheduled_appointment_cannot_be_deactivated(monkeypatch) -> None:
  monkeypatch.setattr(
    AppointmentRepository,
    "has_scheduled_for_citizen",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as exc:
    await AppointmentLifecycleGuard.ensure_user_has_no_scheduled_appointments(
      AsyncMock(),
      uuid.uuid4(),
    )

  assert exc.value.error_code == "USER_HAS_SCHEDULED_APPOINTMENTS"


@pytest.mark.asyncio
async def test_office_with_future_capacity_cannot_be_deactivated(monkeypatch) -> None:
  monkeypatch.setattr(
    AppointmentRepository,
    "has_scheduled_for_office",
    AsyncMock(return_value=False),
  )
  monkeypatch.setattr(
    AppointmentSlotRepository,
    "has_future_available_slots",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as exc:
    await AppointmentLifecycleGuard.ensure_office_has_no_appointment_commitments(
      AsyncMock(),
      uuid.uuid4(),
    )

  assert exc.value.error_code == "OFFICE_HAS_APPOINTMENT_COMMITMENTS"
