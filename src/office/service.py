import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DomainException
from src.office.models import Office, OfficeHistory
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.office.repository import OfficeRepository

class OfficeService:
  """
  Handles business logic for office management, including audit trails and soft deletion.
  Delegates all database access to the OfficeRepository.
  """

  @staticmethod
  async def create_office(
    db: AsyncSession, 
    office_data: OfficeCreate, 
    admin_id: uuid.UUID
  ) -> Office:
    """
    Creates a new office and initializes its audit trail.
    Enforces name uniqueness across the department structure.
    """
    existing_office = await OfficeRepository.get_by_name(db, office_data.name)
    if existing_office:
      raise DomainException("An office with this name already exists", status_code=400)

    new_office = Office(
      name=office_data.name,
      description=office_data.description
    )
    
    OfficeRepository.add(db, new_office)
    await db.flush() 

    history_entry = OfficeHistory(
      office_id=new_office.id,
      name=new_office.name,
      description=new_office.description,
      changed_by_user_id=admin_id,
      change_reason="Initial office creation"
    )
    
    OfficeRepository.add_history(db, history_entry)
    
    await db.commit()
    await db.refresh(new_office)
    
    return new_office

  @staticmethod
  async def get_all_offices(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    include_inactive: bool = False
  ):
    """
    Retrieves a paginated list of offices.
    """
    return await OfficeRepository.get_all(db, skip, limit, include_inactive)

  @staticmethod
  async def get_office_by_id(db: AsyncSession, office_id: uuid.UUID) -> Office:
    """
    Retrieves a specific office and ensures its existence.
    """
    office = await OfficeRepository.get_by_id(db, office_id)
    if not office:
      raise DomainException("Office not found", status_code=404)
    return office

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

    for key, value in update_dict.items():
      setattr(office, key, value)
      
    history_entry = OfficeHistory(
      office_id=office.id,
      name=office.name,
      description=office.description,
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
      name=f"deleted_{office.id}_{office.name}",
      description=office.description,
      changed_by_user_id=admin_id,
      change_reason="Office deactivated"
    )
    
    OfficeRepository.add(db, office)
    OfficeRepository.add_history(db, history_entry)
    await db.commit()