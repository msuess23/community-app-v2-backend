"""Appointment-specific event persistence and projection synchronization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.domain import (
  AppointmentEventType,
  AppointmentState,
  evolve_appointment,
  rebuild_appointment,
)
from src.appointment.models import Appointment, AppointmentEvent
from src.appointment.repository import AppointmentEventRepository, AppointmentRepository
from src.core.exceptions import ResourceNotFoundException


class AppointmentEventStore:
  """Keep appointment event streams and current projections consistent."""

  @staticmethod
  def state_from_appointment(appointment: Appointment) -> AppointmentState:
    """Map a SQLAlchemy projection to pure aggregate state."""

    return AppointmentState(
      current_slot_id=appointment.current_slot_id,
      office_id=appointment.office_id,
      citizen_id=appointment.citizen_id,
      ticket_id=appointment.ticket_id,
      reason=appointment.reason,
      status=appointment.status,
      starts_at=appointment.starts_at,
      ends_at=appointment.ends_at,
      version=appointment.version,
      created_at=appointment.created_at,
      updated_at=appointment.updated_at,
      cancelled_at=appointment.cancelled_at,
      completed_at=appointment.completed_at,
    )

  @staticmethod
  def sync_projection(
    appointment: Appointment,
    state: AppointmentState,
  ) -> None:
    """Copy aggregate values to the query-oriented read model."""

    appointment.current_slot_id = state.current_slot_id
    appointment.office_id = state.office_id
    appointment.citizen_id = state.citizen_id
    appointment.ticket_id = state.ticket_id
    appointment.reason = state.reason
    appointment.status = state.status
    appointment.starts_at = state.starts_at
    appointment.ends_at = state.ends_at
    appointment.version = state.version
    appointment.created_at = state.created_at
    appointment.updated_at = state.updated_at
    appointment.cancelled_at = state.cancelled_at
    appointment.completed_at = state.completed_at

  @staticmethod
  def build_event(
    *,
    appointment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    event_type: AppointmentEventType,
    payload,
    state: AppointmentState,
    occurred_at: datetime,
  ) -> AppointmentEvent:
    """Build one immutable event after the resulting state is known."""

    return AppointmentEvent(
      id=uuid.uuid4(),
      appointment_id=appointment_id,
      sequence_number=state.version,
      event_type=event_type,
      actor_user_id=actor_user_id,
      occurred_at=occurred_at,
      payload=payload.model_dump(mode="json", exclude_unset=True),
    )

  @staticmethod
  async def create(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    payload,
    occurred_at: datetime | None = None,
  ) -> tuple[Appointment, AppointmentEvent]:
    """Create an appointment projection and its first booking event."""

    event_time = occurred_at or datetime.now(timezone.utc)
    state = evolve_appointment(
      None,
      AppointmentEventType.APPOINTMENT_BOOKED,
      payload,
      occurred_at=event_time,
    )
    appointment = Appointment(id=appointment_id)
    AppointmentEventStore.sync_projection(appointment, state)
    event = AppointmentEventStore.build_event(
      appointment_id=appointment_id,
      actor_user_id=actor_user_id,
      event_type=AppointmentEventType.APPOINTMENT_BOOKED,
      payload=payload,
      state=state,
      occurred_at=event_time,
    )
    AppointmentRepository.add(db, appointment)
    AppointmentEventRepository.add(db, event)
    await db.flush()
    return appointment, event

  @staticmethod
  async def append(
    db: AsyncSession,
    appointment: Appointment,
    *,
    actor_user_id: uuid.UUID,
    event_type: AppointmentEventType,
    payload,
    occurred_at: datetime | None = None,
  ) -> AppointmentEvent:
    """Append a validated event and update the projection in one transaction."""

    event_time = occurred_at or datetime.now(timezone.utc)
    state = evolve_appointment(
      AppointmentEventStore.state_from_appointment(appointment),
      event_type,
      payload,
      occurred_at=event_time,
    )
    AppointmentEventStore.sync_projection(appointment, state)
    event = AppointmentEventStore.build_event(
      appointment_id=appointment.id,
      actor_user_id=actor_user_id,
      event_type=event_type,
      payload=payload,
      state=state,
      occurred_at=event_time,
    )
    AppointmentRepository.add(db, appointment)
    AppointmentEventRepository.add(db, event)
    await db.flush()
    return event

  @staticmethod
  async def rebuild(
    db: AsyncSession,
    appointment_id: uuid.UUID,
  ) -> AppointmentState:
    """Rebuild one appointment solely from persisted events."""

    events = await AppointmentEventRepository.get_events(db, appointment_id)
    if not events:
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    return rebuild_appointment(
      [(event.event_type, event.payload, event.occurred_at) for event in events]
    )
