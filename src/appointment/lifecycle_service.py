"""Lifecycle commands for event-sourced appointments and their occupied slots."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import (
  AppointmentCancelledPayload,
  AppointmentCompletedPayload,
  AppointmentEventType,
  AppointmentMarkedNoShowPayload,
  AppointmentRescheduledPayload,
  AppointmentSlotStatus,
  AppointmentStatus,
)
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment, AppointmentSlot
from src.appointment.repository import AppointmentRepository, AppointmentSlotRepository
from src.appointment.schemas import (
  AppointmentCancelRequest,
  AppointmentCompleteRequest,
  AppointmentNoShowRequest,
  AppointmentRescheduleRequest,
  AppointmentResponse,
)
from src.appointment.service import AppointmentService
from src.core.exceptions import ConflictException, ForbiddenException, ResourceNotFoundException
from src.user.models import User


class AppointmentLifecycleService:
  """Apply the small appointment lifecycle without introducing a workflow engine."""

  @staticmethod
  async def _require_scheduled_for_update(
    db: AsyncSession,
    appointment_id: uuid.UUID,
  ) -> Appointment:
    """Lock and return a scheduled appointment or raise a canonical error."""

    appointment = await AppointmentRepository.get_by_id(
      db,
      appointment_id,
      for_update=True,
    )
    if appointment is None:
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    if appointment.status != AppointmentStatus.SCHEDULED:
      raise ConflictException(
        "Only scheduled appointments can be changed.",
        error_code="APPOINTMENT_NOT_SCHEDULED",
      )
    return appointment

  @staticmethod
  def _require_schedule_access(
    appointment: Appointment,
    current_user: User,
  ) -> None:
    """Require ownership or responsible-office access for schedule changes."""

    if not AppointmentAccessPolicy.can_change_schedule(appointment, current_user):
      raise ForbiddenException()

  @staticmethod
  def _require_future_change(appointment: Appointment, now: datetime) -> None:
    """Reject citizen-facing schedule changes after the appointment starts."""

    if appointment.starts_at <= now:
      raise ConflictException(
        "The appointment has already started.",
        error_code="APPOINTMENT_ALREADY_STARTED",
      )

  @staticmethod
  async def _lock_current_slot(
    db: AsyncSession,
    appointment: Appointment,
  ) -> AppointmentSlot:
    """Lock the slot currently occupied by a scheduled appointment."""

    if appointment.current_slot_id is None:
      raise ConflictException(
        "The appointment has no current slot.",
        error_code="APPOINTMENT_SLOT_MISSING",
      )
    slot = await AppointmentSlotRepository.get_by_id(
      db,
      appointment.current_slot_id,
      for_update=True,
    )
    if slot is None:
      raise ConflictException(
        "The current appointment slot no longer exists.",
        error_code="APPOINTMENT_SLOT_MISSING",
      )
    return slot

  @staticmethod
  async def reschedule(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    request: AppointmentRescheduleRequest,
    current_user: User,
  ) -> AppointmentResponse:
    """Move one scheduled appointment to a free slot of the same office."""

    appointment = await AppointmentLifecycleService._require_scheduled_for_update(
      db,
      appointment_id,
    )
    AppointmentLifecycleService._require_schedule_access(appointment, current_user)
    now = datetime.now(timezone.utc)
    AppointmentLifecycleService._require_future_change(appointment, now)

    if appointment.current_slot_id == request.target_slot_id:
      raise ConflictException(
        "The target slot is already assigned to this appointment.",
        error_code="APPOINTMENT_SLOT_UNCHANGED",
      )
    if appointment.current_slot_id is None:
      raise ConflictException(
        "The appointment has no current slot.",
        error_code="APPOINTMENT_SLOT_MISSING",
      )

    # Both rows are locked in deterministic UUID order so concurrent moves to
    # the same target slot serialize without lock inversion.
    slots = await AppointmentSlotRepository.get_many_for_update(
      db,
      [appointment.current_slot_id, request.target_slot_id],
    )
    current_slot = slots.get(appointment.current_slot_id)
    target_slot = slots.get(request.target_slot_id)
    if current_slot is None or target_slot is None:
      raise ResourceNotFoundException(
        "Appointment slot not found",
        error_code="APPOINTMENT_SLOT_NOT_FOUND",
      )
    if current_slot.status != AppointmentSlotStatus.BOOKED:
      raise ConflictException(
        "The current slot is not booked.",
        error_code="APPOINTMENT_SLOT_STATE_INVALID",
      )
    if target_slot.office_id != appointment.office_id:
      raise ConflictException(
        "The target slot belongs to another office.",
        error_code="APPOINTMENT_SLOT_OFFICE_MISMATCH",
      )
    if target_slot.status != AppointmentSlotStatus.AVAILABLE:
      raise ConflictException(
        "The target slot is not available.",
        error_code="APPOINTMENT_SLOT_NOT_AVAILABLE",
      )
    if target_slot.starts_at <= now:
      raise ConflictException(
        "The target slot is in the past.",
        error_code="APPOINTMENT_SLOT_IN_PAST",
      )

    payload = AppointmentRescheduledPayload(
      previous_slot_id=current_slot.id,
      new_slot_id=target_slot.id,
      previous_starts_at=current_slot.starts_at,
      previous_ends_at=current_slot.ends_at,
      new_starts_at=target_slot.starts_at,
      new_ends_at=target_slot.ends_at,
      reason=request.reason,
    )
    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=current_user.id,
      event_type=AppointmentEventType.APPOINTMENT_RESCHEDULED,
      payload=payload,
      occurred_at=now,
    )
    current_slot.status = AppointmentSlotStatus.AVAILABLE
    current_slot.updated_at = now
    target_slot.status = AppointmentSlotStatus.BOOKED
    target_slot.updated_at = now
    await db.flush()

    return AppointmentService.to_response(appointment, current_user=current_user, now=now)

  @staticmethod
  async def cancel(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    request: AppointmentCancelRequest,
    current_user: User,
  ) -> AppointmentResponse:
    """Cancel a future appointment and make its slot available again."""

    appointment = await AppointmentLifecycleService._require_scheduled_for_update(
      db,
      appointment_id,
    )
    AppointmentLifecycleService._require_schedule_access(appointment, current_user)
    now = datetime.now(timezone.utc)
    AppointmentLifecycleService._require_future_change(appointment, now)
    slot = await AppointmentLifecycleService._lock_current_slot(db, appointment)
    if slot.status != AppointmentSlotStatus.BOOKED:
      raise ConflictException(
        "The current slot is not booked.",
        error_code="APPOINTMENT_SLOT_STATE_INVALID",
      )

    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=current_user.id,
      event_type=AppointmentEventType.APPOINTMENT_CANCELLED,
      payload=AppointmentCancelledPayload(slot_id=slot.id, reason=request.reason),
      occurred_at=now,
    )
    slot.status = AppointmentSlotStatus.AVAILABLE
    slot.updated_at = now
    await db.flush()

    return AppointmentService.to_response(appointment, current_user=current_user, now=now)

  @staticmethod
  async def _record_outcome(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    current_user: User,
    event_type: AppointmentEventType,
    payload,
  ) -> AppointmentResponse:
    """Record a terminal office-side outcome and consume the occupied slot."""

    appointment = await AppointmentLifecycleService._require_scheduled_for_update(
      db,
      appointment_id,
    )
    if not AppointmentAccessPolicy.can_record_outcome(appointment, current_user):
      raise ForbiddenException()
    now = datetime.now(timezone.utc)
    if appointment.starts_at > now:
      raise ConflictException(
        "The appointment has not started yet.",
        error_code="APPOINTMENT_NOT_STARTED",
      )
    slot = await AppointmentLifecycleService._lock_current_slot(db, appointment)
    if slot.status != AppointmentSlotStatus.BOOKED:
      raise ConflictException(
        "The current slot is not booked.",
        error_code="APPOINTMENT_SLOT_STATE_INVALID",
      )

    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=current_user.id,
      event_type=event_type,
      payload=payload,
      occurred_at=now,
    )
    slot.status = AppointmentSlotStatus.CONSUMED
    slot.updated_at = now
    await db.flush()

    return AppointmentService.to_response(appointment, current_user=current_user, now=now)

  @staticmethod
  async def complete(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    request: AppointmentCompleteRequest,
    current_user: User,
  ) -> AppointmentResponse:
    """Complete an appointment after its scheduled start."""

    return await AppointmentLifecycleService._record_outcome(
      db,
      appointment_id=appointment_id,
      current_user=current_user,
      event_type=AppointmentEventType.APPOINTMENT_COMPLETED,
      payload=AppointmentCompletedPayload(comment=request.comment),
    )

  @staticmethod
  async def mark_no_show(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    request: AppointmentNoShowRequest,
    current_user: User,
  ) -> AppointmentResponse:
    """Mark a scheduled appointment as a no-show after its start."""

    return await AppointmentLifecycleService._record_outcome(
      db,
      appointment_id=appointment_id,
      current_user=current_user,
      event_type=AppointmentEventType.APPOINTMENT_MARKED_NO_SHOW,
      payload=AppointmentMarkedNoShowPayload(comment=request.comment),
    )
