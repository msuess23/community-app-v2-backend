import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DomainException
from src.office.models import Office, OfficeHistory
from src.office.schemas import OfficeCreate, OfficeUpdate

class OfficeService:
  """
  Handles business logic for office management, including audit trails and soft deletion.
  """

  @staticmethod
  async def create_office(
    db: AsyncSession, 
    office_data: OfficeCreate, 
    admin_id: uuid.UUID
  ) -> Office:
    """
    Creates a new office and initializes its audit trail.
    Ensures that office names remain unique.
    """
    # Check for name collision to prevent duplicate departments
    result = await db.execute(select(Office).where(Office.name == office_data.name))
    if result.scalar_one_or_none():
      raise DomainException("An office with this name already exists", status_code=400)

    new_office = Office(
      name=office_data.name,
      description=office_data.description
    )
    
    db.add(new_office)
    # Flush pushes the object to the database to generate the UUID, 
    # but does not commit the transaction yet. Needed for the history entry.
    await db.flush() 

    history_entry = OfficeHistory(
      office_id=new_office.id,
      name=new_office.name,
      description=new_office.description,
      changed_by_user_id=admin_id,
      change_reason="Initial office creation"
    )
    
    db.add(history_entry)
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
    Retrieves a list of offices.
    Filters out deactivated offices by default, unless explicitly requested.
    """
    query = select(Office)
    
    if not include_inactive:
      query = query.where(Office.is_active == True)
      
    query = query.order_by(Office.name).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

  @staticmethod
  async def get_office_by_id(db: AsyncSession, office_id: uuid.UUID) -> Office:
    """
    Retrieves a specific office by ID.
    """
    result = await db.execute(select(Office).where(Office.id == office_id))
    office = result.scalar_one_or_none()
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
    Applies updates to an office and logs the change in the history table.
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    
    if not update_dict:
      return office
      
    # Check for name uniqueness if the name is being updated
    if "name" in update_dict and update_dict["name"] != office.name:
      result = await db.execute(select(Office).where(Office.name == update_dict["name"]))
      if result.scalar_one_or_none():
        raise DomainException("An office with this name already exists", status_code=400)

    # Apply updates
    for key, value in update_dict.items():
      setattr(office, key, value)
      
    # Create an audit trail snapshot
    history_entry = OfficeHistory(
      office_id=office.id,
      name=office.name,
      description=office.description,
      changed_by_user_id=admin_id,
      change_reason="Office details updated via API"
    )
    
    db.add(office)
    db.add(history_entry)
    await db.commit()
    await db.refresh(office)
    
    return office

  @staticmethod
  async def deactivate_office(
    db: AsyncSession, 
    office_id: uuid.UUID, 
    admin_id: uuid.UUID
  ):
    """
    Soft-deletes (deactivates) an office.
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
      changed_by_user_id=admin_id,
      change_reason="Office deactivated"
    )
    
    db.add(office)
    db.add(history_entry)
    await db.commit()