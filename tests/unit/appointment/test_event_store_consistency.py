from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.appointment.domain import (
  AppointmentCancelledPayload,
  AppointmentEventType,
  AppointmentStatus,
)
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment
from src.core.exceptions import ConflictException


@pytest.mark.asyncio
async def test_append_rejects_appointment_projection_stream_mismatch(monkeypatch) -> None:
  now = datetime.now(timezone.utc)
  appointment = Appointment(
    id=uuid4(),
    current_slot_id=uuid4(),
    office_id=uuid4(),
    citizen_id=uuid4(),
    reason="Consultation",
    status=AppointmentStatus.SCHEDULED,
    starts_at=now + timedelta(days=1),
    ends_at=now + timedelta(days=1, minutes=30),
    version=2,
    created_at=now,
    updated_at=now,
  )
  add_projection = AsyncMock()
  add_event = AsyncMock()
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentEventRepository.get_last_sequence_number",
    AsyncMock(return_value=1),
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentRepository.add",
    add_projection,
  )
  monkeypatch.setattr(
    "src.appointment.repository.AppointmentEventRepository.add",
    add_event,
  )

  with pytest.raises(ConflictException) as exc_info:
    await AppointmentEventStore.append(
      AsyncMock(),
      appointment,
      actor_user_id=appointment.citizen_id,
      event_type=AppointmentEventType.APPOINTMENT_CANCELLED,
      payload=AppointmentCancelledPayload(
        slot_id=appointment.current_slot_id,
        reason="No longer needed",
      ),
    )

  assert exc_info.value.error_code == "APPOINTMENT_PROJECTION_VERSION_MISMATCH"
  add_projection.assert_not_called()
  add_event.assert_not_called()
  assert appointment.version == 2
