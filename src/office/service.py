import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.service import AddressService
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ResourceNotFoundException,
)
from src.core.filters import LifecycleStatusFilter
from src.office.models import Office, OfficeHistory
from src.office.repository import OfficeRepository
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.user.repository import UserRepository


class OfficeService:
  """Handles business logic for office management and audit snapshots."""

  @staticmethod
  def _format_address_snapshot(address) -> str | None:
    if not address:
      return None
    return f"{address.street} {address.house_number}, {address.zip_code} {address.city}"

  @staticmethod
  def _create_history_snapshot(
    office: Office,
    changed_by_user_id: uuid.UUID,
    change_reason: str,
  ) -> OfficeHistory:
    return OfficeHistory(
      office_id=office.id,
      name=office.name,
      description=office.description,
      contact_email=office.contact_email,
      phone=office.phone,
      services=list(office.services or []),
      opening_hours=dict(office.opening_hours or {}),
      address_snapshot=OfficeService._format_address_snapshot(office.address),
      is_active=office.is_active,
      changed_by_user_id=changed_by_user_id,
      change_reason=change_reason,
    )

  @staticmethod
  async def get_all_offices(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
  ):
    return await OfficeRepository.get_all(db, skip, limit, status, search, bbox)

  @staticmethod
  async def get_office_by_id(db: AsyncSession, office_id: uuid.UUID) -> Office:
    office = await OfficeRepository.get_by_id(db, office_id)
    if office is None:
      raise ResourceNotFoundException(
        "Office not found",
        error_code="OFFICE_NOT_FOUND",
      )
    return office

  @staticmethod
  async def create_office(
    db: AsyncSession,
    office_data: OfficeCreate,
    _admin_id: uuid.UUID,
  ) -> Office:
    address_entity = None
    if office_data.address:
      address_entity = AddressService.create_address_entity(office_data.address)
      db.add(address_entity)
      await db.flush()

    new_office = Office(
      name=office_data.name,
      description=office_data.description,
      contact_email=office_data.contact_email,
      phone=office_data.phone,
      services=office_data.services,
      opening_hours=(
        office_data.opening_hours.model_dump(exclude_unset=True)
        if office_data.opening_hours
        else {}
      ),
      address_id=address_entity.id if address_entity else None,
    )
    OfficeRepository.add(db, new_office)
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
    if not office.is_active:
      raise DomainValidationException(
        "Cannot update a deactivated office.",
        error_code="OFFICE_INACTIVE",
      )

    raw_update = update_data.model_dump(
      exclude_unset=True,
      exclude={"change_reason", "address"},
    )
    address_update = (
      update_data.address.model_dump(exclude_unset=True)
      if update_data.address is not None
      else {}
    )
    effective_changes = {
      key: value
      for key, value in raw_update.items()
      if getattr(office, key) != value
    }

    if not effective_changes and not address_update:
      return office

    OfficeRepository.add_history(
      db,
      OfficeService._create_history_snapshot(
        office,
        admin_id,
        update_data.change_reason,
      ),
    )

    if address_update:
      if office.address:
        AddressService.update_address_entity(office.address, update_data.address)
      else:
        new_address = AddressService.create_address_entity(update_data.address)
        db.add(new_address)
        await db.flush()
        office.address_id = new_address.id
        office.address = new_address

    for key, value in effective_changes.items():
      setattr(office, key, value)

    OfficeRepository.add(db, office)
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
    office = await OfficeService.get_office_by_id(db, office_id)

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

    OfficeRepository.add_history(
      db,
      OfficeService._create_history_snapshot(
        office,
        admin_id,
        change_reason,
      ),
    )

    office.is_active = False
    office.deactivated_at = datetime.now(timezone.utc)
    OfficeRepository.add(db, office)
    await db.flush()

  @staticmethod
  async def get_office_history(
    db: AsyncSession,
    office_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> list[OfficeHistory]:
    await OfficeService.get_office_by_id(db, office_id)
    return await OfficeRepository.get_history_by_office_id(
      db,
      office_id,
      start_date,
      end_date,
    )
