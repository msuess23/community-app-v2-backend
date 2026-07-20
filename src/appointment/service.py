"""Booking and query service for event-sourced appointments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import (
  AppointmentAction,
  AppointmentBookedPayload,
  AppointmentSlotStatus,
  AppointmentSortField,
  AppointmentStatus,
)
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment, AppointmentEvent
from src.appointment.repository import (
  AppointmentEventRepository,
  AppointmentRepository,
  AppointmentSlotRepository,
)
from src.appointment.schemas import (
  AppointmentBookRequest,
  AppointmentEventResponse,
  AppointmentResponse,
)
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ForbiddenException,
  ResourceNotFoundException,
)
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.office.repository import OfficeRepository
from src.ticket.domain import TicketStatus
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.user.models import Role, User


class AppointmentService:
  """Book and query event-sourced appointments."""

  @staticmethod
  def allowed_actions(
    appointment: Appointment,
    current_user: User,
    *,
    now: datetime | None = None,
  ) -> list[AppointmentAction]:
    """Return the lifecycle actions currently available to one user."""

    if appointment.status != AppointmentStatus.SCHEDULED:
      return []
    current_time = now or datetime.now(timezone.utc)
    if appointment.starts_at > current_time:
      if AppointmentAccessPolicy.can_change_schedule(appointment, current_user):
        return [AppointmentAction.RESCHEDULE, AppointmentAction.CANCEL]
      return []
    if AppointmentAccessPolicy.can_record_outcome(appointment, current_user):
      return [AppointmentAction.COMPLETE, AppointmentAction.MARK_NO_SHOW]
    return []

  @staticmethod
  def to_response(
    appointment: Appointment,
    *,
    current_user: User,
    now: datetime | None = None,
  ) -> AppointmentResponse:
    """Map one current projection to its role-aware API representation."""

    return AppointmentResponse(
      id=appointment.id,
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
      allowed_actions=AppointmentService.allowed_actions(
        appointment,
        current_user,
        now=now,
      ),
    )

  @staticmethod
  async def _validate_ticket_link(
    db: AsyncSession,
    *,
    ticket_id: uuid.UUID,
    citizen: User,
    office_id: uuid.UUID,
  ) -> None:
    """Validate the immutable optional ticket relation of a booking."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or ticket.creator_user_id != citizen.id:
      raise ResourceNotFoundException(
        "Ticket not found",
        error_code="TICKET_NOT_FOUND",
      )
    if ticket.public_status == TicketStatus.CANCELLED:
      raise DomainValidationException(
        "Cancelled tickets cannot be linked to appointments.",
        error_code="TICKET_CANCELLED",
      )
    if ticket.office_id is None:
      raise DomainValidationException(
        "The ticket must be assigned to an office before booking an appointment.",
        error_code="TICKET_NOT_ASSIGNED",
      )
    if ticket.office_id != office_id:
      raise DomainValidationException(
        "The appointment slot must belong to the ticket's responsible office.",
        error_code="TICKET_OFFICE_MISMATCH",
      )

  @staticmethod
  async def book_slot(
    db: AsyncSession,
    *,
    slot_id: uuid.UUID,
    request: AppointmentBookRequest,
    current_user: User,
  ) -> AppointmentResponse:
    """Book one free slot and create the first appointment event atomically."""

    if current_user.role != Role.CITIZEN:
      raise ForbiddenException("Only citizens may book appointments for themselves")

    slot = await AppointmentSlotRepository.get_by_id(db, slot_id, for_update=True)
    if slot is None:
      raise ResourceNotFoundException(
        "Appointment slot not found",
        error_code="APPOINTMENT_SLOT_NOT_FOUND",
      )
    if slot.status != AppointmentSlotStatus.AVAILABLE:
      raise ConflictException(
        "Appointment slot is not available.",
        error_code="APPOINTMENT_SLOT_NOT_AVAILABLE",
      )
    if slot.starts_at <= datetime.now(timezone.utc):
      raise ConflictException(
        "Appointment slot is in the past.",
        error_code="APPOINTMENT_SLOT_IN_PAST",
      )

    office = await OfficeRepository.get_by_id(db, slot.office_id)
    if office is None or not office.is_active:
      raise ConflictException(
        "The appointment office is inactive.",
        error_code="OFFICE_INACTIVE",
      )

    if request.ticket_id is not None:
      await AppointmentService._validate_ticket_link(
        db,
        ticket_id=request.ticket_id,
        citizen=current_user,
        office_id=slot.office_id,
      )

    appointment_id = uuid.uuid4()
    payload = AppointmentBookedPayload(
      slot_id=slot.id,
      office_id=slot.office_id,
      citizen_id=current_user.id,
      ticket_id=request.ticket_id,
      reason=request.reason,
      starts_at=slot.starts_at,
      ends_at=slot.ends_at,
    )
    appointment, _event = await AppointmentEventStore.create(
      db,
      appointment_id=appointment_id,
      actor_user_id=current_user.id,
      payload=payload,
    )
    slot.status = AppointmentSlotStatus.BOOKED
    slot.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return AppointmentService.to_response(
      appointment,
      current_user=current_user,
    )

  @staticmethod
  async def list_mine(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    status: AppointmentStatus | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    search: str | None,
    sort_by: AppointmentSortField,
    order: SortOrder,
  ) -> PaginatedResponse:
    """Return the current citizen's appointment history."""

    if current_user.role != Role.CITIZEN:
      raise ForbiddenException("Only citizens have a personal appointment list")
    appointments, total = await AppointmentRepository.get_citizen_page(
      db,
      citizen_id=current_user.id,
      page=page,
      size=size,
      status=status,
      starts_from=starts_from,
      starts_to=starts_to,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    return PaginatedResponse.create(
      data=[
        AppointmentService.to_response(item, current_user=current_user)
        for item in appointments
      ],
      total=total,
      page=page,
      size=size,
    )

  @staticmethod
  async def list_internal(
    db: AsyncSession,
    *,
    current_user: User,
    office_id: uuid.UUID | None,
    citizen_id: uuid.UUID | None,
    ticket_id: uuid.UUID | None,
    status: AppointmentStatus | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    created_from: datetime | None,
    created_to: datetime | None,
    search: str | None,
    page: int,
    size: int,
    sort_by: AppointmentSortField,
    order: SortOrder,
  ) -> PaginatedResponse:
    """Return the authority list, permanently scoped to the user's office."""

    if current_user.office_id is None or not AppointmentAccessPolicy.can_manage_office(
      current_user.office_id,
      current_user,
    ):
      raise ForbiddenException()
    if office_id is not None and office_id != current_user.office_id:
      raise DomainValidationException(
        "The office filter is outside the current user's scope.",
        error_code="OFFICE_FILTER_OUTSIDE_SCOPE",
      )

    appointments, total = await AppointmentRepository.get_internal_page(
      db,
      office_id=current_user.office_id,
      page=page,
      size=size,
      citizen_id=citizen_id,
      ticket_id=ticket_id,
      status=status,
      starts_from=starts_from,
      starts_to=starts_to,
      created_from=created_from,
      created_to=created_to,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    return PaginatedResponse.create(
      data=[
        AppointmentService.to_response(item, current_user=current_user)
        for item in appointments
      ],
      total=total,
      page=page,
      size=size,
    )

  @staticmethod
  def event_response(
    event: AppointmentEvent,
    *,
    include_actor: bool,
  ) -> AppointmentEventResponse:
    """Map one event while hiding authority identifiers from citizens."""

    return AppointmentEventResponse(
      id=event.id,
      sequence_number=event.sequence_number,
      event_type=event.event_type,
      actor_user_id=event.actor_user_id if include_actor else None,
      occurred_at=event.occurred_at,
      payload=dict(event.payload),
    )

  @staticmethod
  async def get_events(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    current_user: User,
    page: int,
    size: int,
  ) -> PaginatedResponse[AppointmentEventResponse]:
    """Return a chronological event page to the owner or responsible office."""

    appointment = await AppointmentRepository.get_by_id(db, appointment_id)
    if appointment is None or not AppointmentAccessPolicy.can_view(
      appointment,
      current_user,
    ):
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    events, total = await AppointmentEventRepository.get_event_page(
      db,
      appointment_id,
      page=page,
      size=size,
    )
    include_actor = AppointmentAccessPolicy.can_manage_office(
      appointment.office_id,
      current_user,
    )
    return PaginatedResponse.create(
      data=[
        AppointmentService.event_response(event, include_actor=include_actor)
        for event in events
      ],
      total=total,
      page=page,
      size=size,
    )

  @staticmethod
  async def get_appointment(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    current_user: User,
  ) -> AppointmentResponse:
    """Return an appointment visible to its citizen or responsible office."""

    appointment = await AppointmentRepository.get_by_id(db, appointment_id)
    if appointment is None:
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    if not AppointmentAccessPolicy.can_view(appointment, current_user):
      raise ForbiddenException()
    return AppointmentService.to_response(
      appointment,
      current_user=current_user,
    )
