"""Pure event evolution tests for the appointment aggregate."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.appointment.domain import (
  AppointmentBookedPayload,
  AppointmentCancelledPayload,
  AppointmentCompletedPayload,
  AppointmentEventType,
  AppointmentRescheduledPayload,
  AppointmentStatus,
  evolve_appointment,
  rebuild_appointment,
)


def _booking_payload(now: datetime) -> AppointmentBookedPayload:
  return AppointmentBookedPayload(
    slot_id=uuid.uuid4(),
    office_id=uuid.uuid4(),
    citizen_id=uuid.uuid4(),
    ticket_id=uuid.uuid4(),
    reason="Discuss road damage",
    starts_at=now + timedelta(days=2),
    ends_at=now + timedelta(days=2, minutes=30),
  )


def test_appointment_rebuild_matches_sequential_evolution() -> None:
  now = datetime.now(timezone.utc)
  booking = _booking_payload(now)
  second_slot_id = uuid.uuid4()
  rescheduled = AppointmentRescheduledPayload(
    previous_slot_id=booking.slot_id,
    new_slot_id=second_slot_id,
    previous_starts_at=booking.starts_at,
    previous_ends_at=booking.ends_at,
    new_starts_at=now + timedelta(days=3),
    new_ends_at=now + timedelta(days=3, minutes=30),
    reason="Citizen requested another day",
  )
  completed = AppointmentCompletedPayload(comment="Request accepted")

  state = rebuild_appointment(
    [
      (AppointmentEventType.APPOINTMENT_BOOKED, booking.model_dump(mode="json"), now),
      (
        AppointmentEventType.APPOINTMENT_RESCHEDULED,
        rescheduled.model_dump(mode="json"),
        now + timedelta(minutes=1),
      ),
      (
        AppointmentEventType.APPOINTMENT_COMPLETED,
        completed.model_dump(mode="json"),
        now + timedelta(days=3, minutes=31),
      ),
    ]
  )

  assert state.current_slot_id == second_slot_id
  assert state.status == AppointmentStatus.COMPLETED
  assert state.version == 3
  assert state.completed_at == now + timedelta(days=3, minutes=31)


def test_cancellation_must_reference_current_slot() -> None:
  now = datetime.now(timezone.utc)
  booking = _booking_payload(now)
  state = evolve_appointment(
    None,
    AppointmentEventType.APPOINTMENT_BOOKED,
    booking,
    occurred_at=now,
  )

  with pytest.raises(ValueError, match="current slot"):
    evolve_appointment(
      state,
      AppointmentEventType.APPOINTMENT_CANCELLED,
      AppointmentCancelledPayload(
        slot_id=uuid.uuid4(),
        reason="No longer needed",
      ),
      occurred_at=now + timedelta(minutes=1),
    )


def test_booking_is_the_only_valid_initial_event() -> None:
  now = datetime.now(timezone.utc)

  with pytest.raises(ValueError, match="requires an existing"):
    evolve_appointment(
      None,
      AppointmentEventType.APPOINTMENT_COMPLETED,
      AppointmentCompletedPayload(comment=None),
      occurred_at=now,
    )
