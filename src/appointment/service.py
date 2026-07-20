"""Application services for appointment slots and initial bookings."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import (
  AppointmentBookedPayload,
  AppointmentSlotSortField,
  AppointmentSlotStatus,
  AppointmentSortField,
  AppointmentStatus,
)
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment, AppointmentSlot
from src.appointment.repository import AppointmentRepository, AppointmentSlotRepository
from src.appointment.schemas import (
  AppointmentBookRequest,
  AppointmentResponse,
  AppointmentSlotBatchCreate,
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


class AppointmentSlotService:
  """Manage office slot capacity without introducing event sourcing."""

  @staticmethod
  async def list_slots(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    current_user: User | None,
    page: int,
    size: int,
    status: AppointmentSlotStatus | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    sort_by: AppointmentSlotSortField,
    order: SortOrder,
  ) -> PaginatedResponse:
    """List public availability or the complete office-owned slot view."""

    office = await OfficeRepository.get_by_id(db, office_id)
    if office is None or not office.is_active:
      raise ResourceNotFoundException(
        "Office not found",
        error_code="OFFICE_NOT_FOUND",
      )

    can_manage = (
      current_user is not None
      and AppointmentAccessPolicy.can_manage_office(office_id, current_user)
    )
    if status not in {None, AppointmentSlotStatus.AVAILABLE} and not can_manage:
      raise ForbiddenException("Only office case workers may inspect unavailable slots")

    slots, total = await AppointmentSlotRepository.get_page(
      db,
      office_id=office_id,
      page=page,
      size=size,
      status=status,
      starts_from=starts_from,
      starts_to=starts_to,
      public_only=not can_manage,
      sort_by=sort_by,
      order=order,
    )
    return PaginatedResponse.create(data=slots, total=total, page=page, size=size)

  @staticmethod
  async def create_slots(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    request: AppointmentSlotBatchCreate,
    current_user: User,
  ) -> list[AppointmentSlot]:
    """Create a non-overlapping slot batch while locking the owning office."""

    office = await AppointmentSlotRepository.get_office_for_update(db, office_id)
    if office is None:
      raise ResourceNotFoundException(
        "Office not found",
        error_code="OFFICE_NOT_FOUND",
      )
    if not office.is_active:
      raise DomainValidationException(
        "Cannot create slots for an inactive office.",
        error_code="OFFICE_INACTIVE",
      )
    if not AppointmentAccessPolicy.can_manage_office(office_id, current_user):
      raise ForbiddenException()

    now = datetime.now(timezone.utc)
    ordered = sorted(request.slots, key=lambda slot: slot.starts_at)
    for index, slot in enumerate(ordered):
      if slot.starts_at <= now:
        raise DomainValidationException(
          "Appointment slots must start in the future.",
          error_code="APPOINTMENT_SLOT_NOT_FUTURE",
        )
      if index and slot.starts_at < ordered[index - 1].ends_at:
        raise DomainValidationException(
          "The slot batch contains overlapping intervals.",
          error_code="APPOINTMENT_SLOT_OVERLAP",
        )
      if await AppointmentSlotRepository.has_overlap(
        db,
        office_id=office_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
      ):
        raise ConflictException(
          "The appointment slot overlaps an existing slot.",
          error_code="APPOINTMENT_SLOT_OVERLAP",
        )

    entities = [
      AppointmentSlot(
        id=uuid.uuid4(),
        office_id=office_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        status=AppointmentSlotStatus.AVAILABLE,
        created_by_user_id=current_user.id,
      )
      for slot in ordered
    ]
    AppointmentSlotRepository.add_all(db, entities)
    await db.flush()
    return entities

  @staticmethod
  async def deactivate_slot(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    slot_id: uuid.UUID,
    current_user: User,
  ) -> None:
    """Deactivate one future free slot without deleting audit-relevant rows."""

    slot = await AppointmentSlotRepository.get_by_id(db, slot_id, for_update=True)
    if slot is None or slot.office_id != office_id:
      raise ResourceNotFoundException(
        "Appointment slot not found",
        error_code="APPOINTMENT_SLOT_NOT_FOUND",
      )
    if not AppointmentAccessPolicy.can_manage_office(office_id, current_user):
      raise ForbiddenException()
    if slot.status != AppointmentSlotStatus.AVAILABLE:
      raise ConflictException(
        "Only available slots can be deactivated.",
        error_code="APPOINTMENT_SLOT_NOT_AVAILABLE",
      )
    if slot.starts_at <= datetime.now(timezone.utc):
      raise ConflictException(
        "Past appointment slots cannot be deactivated.",
        error_code="APPOINTMENT_SLOT_IN_PAST",
      )

    slot.status = AppointmentSlotStatus.INACTIVE
    slot.updated_at = datetime.now(timezone.utc)
    await db.flush()


class AppointmentService:
  """Book and query event-sourced appointments."""

  @staticmethod
  def to_response(appointment: Appointment) -> AppointmentResponse:
    """Map one current projection to its API representation."""

    # Lifecycle commands are introduced in Appointment Patch 2. Until then,
    # the server deliberately advertises no post-booking mutations.
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
      allowed_actions=[],
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
    return AppointmentService.to_response(appointment)

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
      data=[AppointmentService.to_response(item) for item in appointments],
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
      data=[AppointmentService.to_response(item) for item in appointments],
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
    return AppointmentService.to_response(appointment)
