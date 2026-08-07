"""Pure appointment state evolution and deterministic event replay."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.appointment.domain.enums import AppointmentEventType, AppointmentStatus
from src.appointment.domain.payloads import (
  AppointmentBookedPayload,
  AppointmentCancelledPayload,
  AppointmentRescheduledPayload,
  validate_appointment_event_payload,
)


class AppointmentState(BaseModel):
  """Pure aggregate state reconstructed from appointment events."""

  model_config = ConfigDict(validate_assignment=True)

  current_slot_id: UUID | None
  office_id: UUID
  citizen_id: UUID
  ticket_id: UUID | None = None
  reason: str | None = None
  status: AppointmentStatus
  starts_at: datetime
  ends_at: datetime
  version: int
  created_at: datetime
  updated_at: datetime
  cancelled_at: datetime | None = None
  completed_at: datetime | None = None


def evolve_appointment(
  state: AppointmentState | None,
  event_type: AppointmentEventType,
  payload: BaseModel | dict[str, Any],
  *,
  occurred_at: datetime,
) -> AppointmentState:
  """Apply one validated event and return the resulting appointment state."""

  validated = validate_appointment_event_payload(event_type, payload)

  if event_type == AppointmentEventType.APPOINTMENT_BOOKED:
    if state is not None:
      raise ValueError("APPOINTMENT_BOOKED must be the first aggregate event")
    booked = validated
    assert isinstance(booked, AppointmentBookedPayload)
    if booked.ends_at <= booked.starts_at:
      raise ValueError("Appointment end must be after its start")
    return AppointmentState(
      current_slot_id=booked.slot_id,
      office_id=booked.office_id,
      citizen_id=booked.citizen_id,
      ticket_id=booked.ticket_id,
      reason=booked.reason,
      status=AppointmentStatus.SCHEDULED,
      starts_at=booked.starts_at,
      ends_at=booked.ends_at,
      version=1,
      created_at=occurred_at,
      updated_at=occurred_at,
    )

  if state is None:
    raise ValueError(f"{event_type.value} requires an existing appointment state")

  next_state = state.model_copy(deep=True)
  next_state.version += 1
  next_state.updated_at = occurred_at

  if event_type == AppointmentEventType.APPOINTMENT_RESCHEDULED:
    rescheduled = validated
    assert isinstance(rescheduled, AppointmentRescheduledPayload)
    if next_state.status != AppointmentStatus.SCHEDULED:
      raise ValueError("Only scheduled appointments can be rescheduled")
    if next_state.current_slot_id != rescheduled.previous_slot_id:
      raise ValueError("Reschedule payload does not match the current slot")
    if rescheduled.new_ends_at <= rescheduled.new_starts_at:
      raise ValueError("Appointment end must be after its start")
    next_state.current_slot_id = rescheduled.new_slot_id
    next_state.starts_at = rescheduled.new_starts_at
    next_state.ends_at = rescheduled.new_ends_at
  elif event_type == AppointmentEventType.APPOINTMENT_CANCELLED:
    cancelled = validated
    assert isinstance(cancelled, AppointmentCancelledPayload)
    if next_state.status != AppointmentStatus.SCHEDULED:
      raise ValueError("Only scheduled appointments can be cancelled")
    if next_state.current_slot_id != cancelled.slot_id:
      raise ValueError("Cancellation payload does not match the current slot")
    next_state.current_slot_id = None
    next_state.status = AppointmentStatus.CANCELLED
    next_state.cancelled_at = occurred_at
  elif event_type == AppointmentEventType.APPOINTMENT_COMPLETED:
    if next_state.status != AppointmentStatus.SCHEDULED:
      raise ValueError("Only scheduled appointments can be completed")
    next_state.status = AppointmentStatus.COMPLETED
    next_state.completed_at = occurred_at
  elif event_type == AppointmentEventType.APPOINTMENT_MARKED_NO_SHOW:
    if next_state.status != AppointmentStatus.SCHEDULED:
      raise ValueError("Only scheduled appointments can be marked as no-show")
    next_state.status = AppointmentStatus.NO_SHOW
    next_state.completed_at = occurred_at
  elif event_type == AppointmentEventType.DOCUMENT_VERSION_ADDED:
    # Documents belong to the same audit stream but do not change scheduling data.
    pass
  else:  # pragma: no cover - exhaustive guard for future enum additions
    raise ValueError(f"Unsupported appointment event: {event_type.value}")

  return next_state


def rebuild_appointment(
  events: Sequence[tuple[AppointmentEventType, dict[str, Any], datetime]],
) -> AppointmentState:
  """Rebuild an appointment from its ordered append-only event stream."""

  state: AppointmentState | None = None
  for event_type, payload, occurred_at in events:
    state = evolve_appointment(
      state,
      event_type,
      payload,
      occurred_at=occurred_at,
    )
  if state is None:
    raise ValueError("Cannot rebuild an appointment without events")
  return state
