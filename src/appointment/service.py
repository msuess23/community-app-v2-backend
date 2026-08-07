"""Booking and query service for event-sourced appointments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import (
  AppointmentAction,
  AppointmentBookedPayload,
  AppointmentEventType,
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
  AppointmentFilterOptionsResponse,
  AppointmentOfficeReference,
  AppointmentResponse,
  AppointmentTicketReference,
  AppointmentUserReference,
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
from src.ticket.models import Ticket
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.services.access_policy import TicketAccessPolicy
from src.user.models import Role, User
from src.user.repository import UserRepository


class AppointmentService:
  """Book and query event-sourced appointments."""

  @staticmethod
  def _user_reference(user: User | None, user_id: uuid.UUID) -> AppointmentUserReference:
    """Return a data-minimizing label with a safe historical fallback."""

    if user is None:
      return AppointmentUserReference(id=user_id, display_name="Unknown user")
    return AppointmentUserReference(
      id=user.id,
      display_name=f"{user.first_name} {user.last_name}".strip(),
    )

  @staticmethod
  def _office_reference(appointment: Appointment) -> AppointmentOfficeReference:
    """Return the eagerly loaded office label without exposing full master data."""

    office = getattr(appointment, "office", None)
    return AppointmentOfficeReference(
      id=appointment.office_id,
      name=office.name if office is not None else "Unknown office",
    )

  @staticmethod
  def _ticket_reference(
    ticket: Ticket | None,
    *,
    ticket_id: uuid.UUID | None,
    current_user: User,
  ) -> AppointmentTicketReference | None:
    """Return a readable linked-ticket label and current access indication."""

    if ticket_id is None:
      return None
    if ticket is None:
      return AppointmentTicketReference(
        id=ticket_id,
        title="Linked ticket",
        can_view=False,
      )
    return AppointmentTicketReference(
      id=ticket.id,
      title=ticket.title,
      can_view=TicketAccessPolicy.can_view(ticket, current_user),
    )

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

    citizen = getattr(appointment, "citizen", None)
    ticket = getattr(appointment, "ticket", None)
    return AppointmentResponse(
      id=appointment.id,
      current_slot_id=appointment.current_slot_id,
      office_id=appointment.office_id,
      office=AppointmentService._office_reference(appointment),
      citizen_id=appointment.citizen_id,
      citizen=AppointmentService._user_reference(citizen, appointment.citizen_id),
      ticket_id=appointment.ticket_id,
      ticket=AppointmentService._ticket_reference(
        ticket,
        ticket_id=appointment.ticket_id,
        current_user=current_user,
      ),
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
  ) -> Ticket:
    """Validate and return the immutable optional ticket relation of a booking."""

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
    return ticket

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

    linked_ticket: Ticket | None = None
    if request.ticket_id is not None:
      linked_ticket = await AppointmentService._validate_ticket_link(
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
    # The response embeds small references. Assign already loaded objects so the
    # create command does not need a second query after the event append.
    appointment.office = office
    appointment.citizen = current_user
    appointment.ticket = linked_ticket
    appointment.current_slot = slot
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
  def _require_internal_scope(current_user: User) -> uuid.UUID:
    """Return the case worker office or reject users outside appointment staff."""

    if current_user.office_id is None or not AppointmentAccessPolicy.can_manage_office(
      current_user.office_id,
      current_user,
    ):
      raise ForbiddenException()
    return current_user.office_id

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

    scoped_office_id = AppointmentService._require_internal_scope(current_user)
    if office_id is not None and office_id != scoped_office_id:
      raise DomainValidationException(
        "The office filter is outside the current user's scope.",
        error_code="OFFICE_FILTER_OUTSIDE_SCOPE",
      )

    appointments, total = await AppointmentRepository.get_internal_page(
      db,
      office_id=scoped_office_id,
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
  async def get_internal_filter_options(
    db: AsyncSession,
    *,
    current_user: User,
  ) -> AppointmentFilterOptionsResponse:
    """Return readable filters from the caller's complete office appointment scope."""

    office_id = AppointmentService._require_internal_scope(current_user)
    citizen_ids, ticket_ids = (
      await AppointmentRepository.get_internal_filter_reference_ids(
        db,
        office_id=office_id,
      )
    )
    citizens = await UserRepository.get_by_ids(db, citizen_ids)
    tickets = await AppointmentRepository.get_tickets_by_ids(db, ticket_ids)
    citizen_references = sorted(
      [AppointmentService._user_reference(user, user.id) for user in citizens],
      key=lambda item: (item.display_name.casefold(), str(item.id)),
    )
    ticket_references = [
      AppointmentTicketReference(
        id=ticket.id,
        title=ticket.title,
        can_view=TicketAccessPolicy.can_view(ticket, current_user),
      )
      for ticket in tickets
    ]
    ticket_references.sort(
      key=lambda item: (item.title.casefold(), str(item.id))
    )
    return AppointmentFilterOptionsResponse(
      citizens=citizen_references,
      tickets=ticket_references,
    )

  @staticmethod
  def event_response(
    event: AppointmentEvent,
    *,
    include_actor: bool,
  ) -> AppointmentEventResponse:
    """Map one event while redacting staff-only data from citizen responses."""

    payload = dict(event.payload)
    if not include_actor:
      # Storage keys and outcome notes are internal implementation/audit data.
      payload.pop("storage_key", None)
      if event.event_type in {
        AppointmentEventType.APPOINTMENT_COMPLETED,
        AppointmentEventType.APPOINTMENT_MARKED_NO_SHOW,
      }:
        payload.pop("comment", None)
    actor = (
      AppointmentService._user_reference(
        getattr(event, "actor", None),
        event.actor_user_id,
      )
      if include_actor
      else None
    )
    return AppointmentEventResponse(
      id=event.id,
      sequence_number=event.sequence_number,
      event_type=event.event_type,
      actor_user_id=event.actor_user_id if include_actor else None,
      actor=actor,
      occurred_at=event.occurred_at,
      payload=payload,
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
    """Return a newest-first event page to the owner or responsible office."""

    appointment = await AppointmentRepository.get_by_id(db, appointment_id)
    if appointment is None or not AppointmentAccessPolicy.can_view(
      appointment,
      current_user,
    ):
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    include_actor = AppointmentAccessPolicy.can_manage_office(
      appointment.office_id,
      current_user,
    )
    events, total = await AppointmentEventRepository.get_event_page(
      db,
      appointment_id,
      page=page,
      size=size,
      citizen_visible_only=not include_actor,
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
    if appointment is None or not AppointmentAccessPolicy.can_view(
      appointment,
      current_user,
    ):
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    return AppointmentService.to_response(
      appointment,
      current_user=current_user,
    )
