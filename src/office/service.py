import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.service import AddressService
from src.core.exceptions import ConflictException, ResourceNotFoundException
from src.core.filters import LifecycleStatusFilter
from src.core.normalization import normalize_office_name
from src.office.audit import build_office_history
from src.office.models import Office, OfficeHistory
from src.office.repository import OfficeRepository
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.user.persistence import UserPersistence


class OfficeService:
  """Business logic for office lifecycle and temporal audit versions."""

  @staticmethod
  async def _get_locked_office(db: AsyncSession, office_id: uuid.UUID) -> Office:
    office = await OfficeRepository.get_by_id_for_update(db, office_id)
    if office is None:
      raise ResourceNotFoundException(
        "Office not found",
        error_code="OFFICE_NOT_FOUND",
      )
    return office

  @staticmethod
  async def get_all_offices(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
  ):
    return await OfficeRepository.get_all(
      db,
      skip,
      limit,
      status,
      search,
      bbox,
    )

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
    admin_id: uuid.UUID,
  ) -> Office:
    normalized_name = normalize_office_name(office_data.name)
    if await OfficeRepository.get_by_name(db, normalized_name):
      raise ConflictException(
        "An active office with this name already exists",
        error_code="OFFICE_NAME_ALREADY_EXISTS",
      )

    address_entity = None
    if office_data.address:
      address_entity = AddressService.create_address_entity(office_data.address)
      db.add(address_entity)
      await db.flush()

    now = datetime.now(timezone.utc)
    new_office = Office(
      name=normalized_name,
      description=office_data.description,
      contact_email=(
        str(office_data.contact_email)
        if office_data.contact_email is not None
        else None
      ),
      phone=office_data.phone,
      services=list(office_data.services),
      opening_hours=(
        office_data.opening_hours.model_dump(exclude_unset=True)
        if office_data.opening_hours
        else {}
      ),
      address=address_entity,
      created_at=now,
    )
    OfficeRepository.add(db, new_office)
    await db.flush()
    OfficeRepository.add_history(
      db,
      build_office_history(
        new_office,
        actor_id=admin_id,
        change_reason="Initial office creation",
        valid_from=now,
      ),
    )
    await db.flush()
    return new_office

  @staticmethod
  async def update_office(
    db: AsyncSession,
    office: Office,
    update_data: OfficeUpdate,
    admin_id: uuid.UUID,
  ) -> Office:
    locked_office = await OfficeService._get_locked_office(db, office.id)
    if not locked_office.is_active:
      raise ConflictException(
        "Cannot update a deactivated office.",
        error_code="OFFICE_DEACTIVATED",
      )

    changes = update_data.model_dump(
      exclude_unset=True,
      exclude={"change_reason"},
    )
    if not changes:
      return locked_office

    if "name" in changes:
      changes["name"] = normalize_office_name(changes["name"])
      existing_office = await OfficeRepository.get_by_name(
        db,
        changes["name"],
        exclude_id=locked_office.id,
      )
      if existing_office is not None:
        raise ConflictException(
          "An active office with this name already exists",
          error_code="OFFICE_NAME_ALREADY_EXISTS",
        )

    now = datetime.now(timezone.utc)
    await OfficeRepository.close_current_history(
      db,
      locked_office.id,
      valid_to=now,
    )

    address_update = changes.pop("address", None)
    if address_update is not None:
      if locked_office.address:
        AddressService.update_address_entity(
          locked_office.address,
          update_data.address,
        )
      else:
        new_address = AddressService.create_address_entity(update_data.address)
        db.add(new_address)
        await db.flush()
        locked_office.address = new_address

    for key, value in changes.items():
      if key == "opening_hours" and value is not None:
        value = dict(value)
      elif key == "services" and value is not None:
        value = list(value)
      elif key == "contact_email" and value is not None:
        value = str(value)
      setattr(locked_office, key, value)

    OfficeRepository.add_history(
      db,
      build_office_history(
        locked_office,
        actor_id=admin_id,
        change_reason=update_data.change_reason,
        valid_from=now,
      ),
    )
    await db.flush()
    return locked_office

  @staticmethod
  async def deactivate_office(
    db: AsyncSession,
    office_id: uuid.UUID,
    admin_id: uuid.UUID,
    *,
    change_reason: str,
  ) -> None:
    office = await OfficeService._get_locked_office(db, office_id)
    if not office.is_active:
      raise ConflictException(
        "Office is already deactivated",
        error_code="OFFICE_ALREADY_DEACTIVATED",
      )

    if await UserPersistence.has_active_users_in_office(db, office.id):
      raise ConflictException(
        "The office still has active staff accounts assigned to it.",
        error_code="OFFICE_HAS_ACTIVE_USERS",
      )

    now = datetime.now(timezone.utc)
    await OfficeRepository.close_current_history(
      db,
      office.id,
      valid_to=now,
    )
    office.is_active = False
    office.deactivated_at = now
    OfficeRepository.add_history(
      db,
      build_office_history(
        office,
        actor_id=admin_id,
        change_reason=change_reason,
        valid_from=now,
      ),
    )
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
