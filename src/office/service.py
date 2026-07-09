import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple

from src.core.exceptions import DomainException
from src.office.models import Office, OfficeHistory
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.office.repository import OfficeRepository
from src.address.service import AddressService
from src.core.filters import LifecycleStatusFilter

class OfficeService:
  """
  Handles business logic for office management, including audit trails and soft deletion.
  Delegates all database access to the OfficeRepository.
  """

  @staticmethod
  def _format_address_snapshot(address) -> str | None:
    """Helper to create a flat string representation of an address for the audit trail."""
    if not address:
      return None
    return f"{address.street} {address.house_number}, {address.zip_code} {address.city}"


  # --- Public Endpoints (no auth required) ---

  @staticmethod
  async def get_all_offices(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None
  ):
    """
    Retrieves a paginated list of offices.
    """
    return await OfficeRepository.get_all(
      db, skip, limit, status, search, bbox
    )

  @staticmethod
  async def get_office_by_id(db: AsyncSession, office_id: uuid.UUID) -> Office:
    """
    Retrieves a specific office and ensures its existence.
    """
    office = await OfficeRepository.get_by_id(db, office_id)
    if not office:
      raise DomainException("Office not found", status_code=404)
    return office


  # --- Admin Endpoints ---

  @staticmethod
  async def create_office(
    db: AsyncSession, 
    office_data: OfficeCreate, 
    admin_id: uuid.UUID
  ) -> Office:
    """
    Creates a new office and initializes its audit trail.
    """
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
      opening_hours=office_data.opening_hours.model_dump(exclude_unset=True) if office_data.opening_hours else {},
      address_id=address_entity.id if address_entity else None
    )
    
    OfficeRepository.add(db, new_office)
    await db.flush() 

    history_entry = OfficeHistory(
      office_id=new_office.id,
      name=new_office.name,
      description=new_office.description,
      contact_email=new_office.contact_email,
      phone=new_office.phone, 
      services=new_office.services,
      opening_hours=new_office.opening_hours,
      address_snapshot=OfficeService._format_address_snapshot(address_entity),
      changed_by_user_id=admin_id,
      change_reason="Initial office creation"
    )
    
    OfficeRepository.add_history(db, history_entry)
    
    await db.commit()
    await db.refresh(new_office)
    
    return new_office


  @staticmethod
  async def update_office(
    db: AsyncSession, 
    office: Office, 
    update_data: OfficeUpdate, 
    admin_id: uuid.UUID
  ) -> Office:
    """
    Applies updates to an office and records a history snapshot.
    """
    if not office.is_active:
      raise DomainException("Cannot update a deactivated office.", status_code=400)

    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
      return office
      
    if "name" in update_dict and update_dict["name"] != office.name:
      existing_office = await OfficeRepository.get_by_name(db, update_dict["name"])
      if existing_office:
        raise DomainException("An office with this name already exists", status_code=400)

    if update_data.address:
      if office.address:
        AddressService.update_address_entity(office.address, update_data.address)
      else:
        new_address = AddressService.create_address_entity(update_data.address)
        db.add(new_address)
        await db.flush()
        office.address_id = new_address.id

    for key, value in update_dict.items():
      if key != "address":
        setattr(office, key, value)
      
    history_entry = OfficeHistory(
      office_id=office.id,
      name=office.name,
      description=office.description,
      contact_email=office.contact_email,
      phone=office.phone,
      services=office.services,
      opening_hours=office.opening_hours,
      address_snapshot=OfficeService._format_address_snapshot(office.address),
      changed_by_user_id=admin_id,
      change_reason="Office details updated via API"
    )
    
    OfficeRepository.add(db, office)
    OfficeRepository.add_history(db, history_entry)
    await db.commit()
    await db.refresh(office)
    return office


  @staticmethod
  async def deactivate_office(
    db: AsyncSession, 
    office_id: uuid.UUID, 
    admin_id: uuid.UUID
  ) -> None:
    """
    Soft-deletes (deactivates) an office and creates an audit entry.
    """
    office = await OfficeService.get_office_by_id(db, office_id)
    
    if not office.is_active:
      raise DomainException("Office is already deactivated", status_code=400)
      
    office.is_active = False
    office.deactivated_at = datetime.now(timezone.utc)

    history_entry = OfficeHistory(
      office_id=office.id,
      name=office.name,
      description=office.description,
      address_snapshot=OfficeService._format_address_snapshot(office.address),
      changed_by_user_id=admin_id,
      change_reason="Office deactivated"
    )
    
    OfficeRepository.add(db, office)
    OfficeRepository.add_history(db, history_entry)
    await db.commit()


  @staticmethod
  async def get_office_history(
    db: AsyncSession, 
    office_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
  ) -> list[OfficeHistory]:
    """
    Retrieves the audit trail of an office.
    Ensures the office actually exists before returning history.
    """
    await OfficeService.get_office_by_id(db, office_id)
    return await OfficeRepository.get_history_by_office_id(db, office_id, start_date, end_date)