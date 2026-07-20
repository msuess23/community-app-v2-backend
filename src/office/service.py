import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.service import AddressService
from src.appointment.lifecycle_guard import AppointmentLifecycleGuard
from src.address.snapshot import AddressSnapshot
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ResourceNotFoundException,
)
from src.core.filters import LifecycleStatusFilter, SortOrder
from src.core.schemas import PaginatedResponse
from src.office.models import Office, OfficeHistory, OfficeSortField
from src.office.repository import OfficeRepository
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.ticket.services.lifecycle_guard import TicketLifecycleGuard
from src.user.models import Role, User
from src.user.repository import UserRepository


class OfficeService:
  """Handles office management and append-only result-state snapshots."""

  @staticmethod
  def add_history_snapshot(
    db: AsyncSession,
    office: Office,
    *,
    changed_by_user_id: uuid.UUID,
    change_reason: str,
  ) -> OfficeHistory:
    """Capture the current office state as an immutable history row."""

    snapshot = OfficeHistory(
      office_id=office.id,
      name=office.name,
      description=office.description,
      contact_email=office.contact_email,
      phone=office.phone,
      services=list(office.services or []),
      opening_hours=dict(office.opening_hours or {}),
      address_snapshot=(
        AddressSnapshot.from_address(office.address).model_dump(mode="json")
        if office.address is not None
        else None
      ),
      is_active=office.is_active,
      changed_by_user_id=changed_by_user_id,
      change_reason=change_reason,
    )
    OfficeRepository.add_history(db, snapshot)
    return snapshot

  @staticmethod
  async def get_all_offices(
    db: AsyncSession,
    *,
    current_user: User | None,
    page: int = 1,
    size: int = 20,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    sort_by: OfficeSortField = OfficeSortField.NAME,
    order: SortOrder = SortOrder.ASC,
  ) -> PaginatedResponse:
    """Return offices visible to the caller with search and pagination."""

    if (
      (current_user is None or current_user.role != Role.ADMIN)
      and status != LifecycleStatusFilter.ACTIVE
    ):
      raise DomainValidationException(
        "Only administrators may filter inactive offices.",
        error_code="LIFECYCLE_FILTER_NOT_ALLOWED",
      )

    effective_status = (
      status
      if current_user is not None and current_user.role == Role.ADMIN
      else LifecycleStatusFilter.ACTIVE
    )
    offices, total = await OfficeRepository.get_page(
      db,
      page=page,
      size=size,
      status=effective_status,
      search=search,
      bbox=bbox,
      sort_by=sort_by,
      order=order,
    )
    return PaginatedResponse.create(data=offices, total=total, page=page, size=size)

  @staticmethod
  async def get_office_by_id(
    db: AsyncSession,
    office_id: uuid.UUID,
    *,
    include_inactive: bool = False,
  ) -> Office:
    """Load one office according to lifecycle visibility rules."""

    office = await OfficeRepository.get_by_id(db, office_id)
    if office is None or (not include_inactive and not office.is_active):
      raise ResourceNotFoundException(
        "Office not found",
        error_code="OFFICE_NOT_FOUND",
      )
    return office

  @staticmethod
  async def create_office(
    db: AsyncSession,
    office_data: OfficeCreate,
    admin_id: uuid.UUID,
  ) -> Office:
    """Create an office, optional address, and initial history snapshot."""

    address_entity = None
    if office_data.address:
      address_entity = AddressService.create_address_entity(office_data.address)
      db.add(address_entity)
      await db.flush()

    new_office = Office(
      name=office_data.name,
      description=office_data.description,
      contact_email=(str(office_data.contact_email).lower() if office_data.contact_email else None),
      phone=office_data.phone,
      services=office_data.services,
      opening_hours=(office_data.opening_hours.model_dump(exclude_none=True) if office_data.opening_hours else {}),
      address=address_entity,
      is_active=True,
    )
    OfficeRepository.add(db, new_office)
    await db.flush()
    OfficeService.add_history_snapshot(
      db,
      new_office,
      changed_by_user_id=admin_id,
      change_reason="OFFICE_CREATED",
    )
    await db.flush()
    await db.refresh(new_office)
    return new_office

  @staticmethod
  async def update_office(
    db: AsyncSession,
    office: Office,
    update_data: OfficeUpdate,
    admin_id: uuid.UUID,
  ) -> Office:
    """Update an office and preserve its previous state in history."""

    if not office.is_active:
      raise DomainValidationException(
        "Cannot update a deactivated office.",
        error_code="OFFICE_INACTIVE",
      )

    raw_update = update_data.model_dump(
      exclude_unset=True,
      exclude={"change_reason", "address", "opening_hours", "contact_email"},
    )
    if "contact_email" in update_data.model_fields_set:
      raw_update["contact_email"] = (
        str(update_data.contact_email).lower()
        if update_data.contact_email is not None
        else None
      )
    if "opening_hours" in update_data.model_fields_set:
      raw_update["opening_hours"] = (
        update_data.opening_hours.model_dump(exclude_none=True)
        if update_data.opening_hours is not None
        else {}
      )

    effective_changes = {
      key: value
      for key, value in raw_update.items()
      if getattr(office, key) != value
    }
    address_was_supplied = "address" in update_data.model_fields_set
    address_changes = False
    if address_was_supplied:
      if update_data.address is None:
        address_changes = office.address is not None
      else:
        address_changes = bool(update_data.address.model_dump(exclude_unset=True))

    if not effective_changes and not address_changes:
      return office

    if address_was_supplied:
      if update_data.address is None:
        # Replacing the owned relationship lets delete-orphan remove the old row.
        office.address = None
      elif office.address:
        AddressService.update_address_entity(office.address, update_data.address)
      else:
        office.address = AddressService.create_address_from_update(update_data.address)

    for key, value in effective_changes.items():
      setattr(office, key, value)

    OfficeRepository.add(db, office)
    await db.flush()
    OfficeService.add_history_snapshot(
      db,
      office,
      changed_by_user_id=admin_id,
      change_reason=update_data.change_reason,
    )
    await db.flush()
    await db.refresh(office)
    return office

  @staticmethod
  async def deactivate_office(
    db: AsyncSession,
    office_id: uuid.UUID,
    admin_id: uuid.UUID,
    change_reason: str,
  ) -> None:
    """Deactivate an office after enforcing dependent-resource guards."""

    office = await OfficeService.get_office_by_id(
      db,
      office_id,
      include_inactive=True,
    )

    if not office.is_active:
      raise ConflictException(
        "Office is already deactivated",
        error_code="OFFICE_ALREADY_DEACTIVATED",
      )

    if await UserRepository.has_active_users_for_office(db, office.id):
      raise ConflictException(
        "Office cannot be deactivated while active users are assigned to it.",
        error_code="OFFICE_HAS_ACTIVE_USERS",
      )

    await TicketLifecycleGuard.ensure_office_has_no_active_tickets(db, office.id)
    await AppointmentLifecycleGuard.ensure_office_has_no_appointment_commitments(
      db,
      office.id,
    )

    office.is_active = False
    office.deactivated_at = datetime.now(timezone.utc)
    OfficeRepository.add(db, office)
    await db.flush()
    OfficeService.add_history_snapshot(
      db,
      office,
      changed_by_user_id=admin_id,
      change_reason=change_reason,
    )
    await db.flush()

  @staticmethod
  async def get_office_history(
    db: AsyncSession,
    office_id: uuid.UUID,
    *,
    page: int,
    size: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> PaginatedResponse:
    """Return a paginated append-only history for one office."""

    await OfficeService.get_office_by_id(db, office_id, include_inactive=True)
    history, total = await OfficeRepository.get_history_page(
      db,
      office_id,
      page=page,
      size=size,
      start_date=start_date,
      end_date=end_date,
    )
    return PaginatedResponse.create(
      data=history,
      total=total,
      page=page,
      size=size,
    )
