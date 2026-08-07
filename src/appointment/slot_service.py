"""Application service for ordinary office appointment-slot capacity."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import AppointmentSlotSortField, AppointmentSlotStatus
from src.appointment.models import AppointmentSlot
from src.appointment.repository import AppointmentSlotRepository
from src.appointment.schemas import AppointmentSlotBatchCreate
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ForbiddenException,
  ResourceNotFoundException,
)
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.office.repository import OfficeRepository
from src.user.models import User


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
