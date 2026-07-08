import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.office.models import Office, OfficeHistory
from src.address.models import Address
from src.core.filters import apply_bbox_filter, apply_search_filter

class OfficeRepository:
  """
  Data access layer for Office and OfficeHistory entities.
  """

  @staticmethod
  async def get_by_id(db: AsyncSession, office_id: uuid.UUID) -> Optional[Office]:
    result = await db.execute(
      select(Office).options(selectinload(Office.address)).where(Office.id == office_id)
    )
    return result.scalar_one_or_none()


  @staticmethod
  async def get_by_name(db: AsyncSession, name: str) -> Optional[Office]:
    result = await db.execute(
      select(Office).options(selectinload(Office.address)).where(Office.name == name)
    )
    return result.scalar_one_or_none()


  @staticmethod
  async def get_all(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    include_inactive: bool = False,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None
  ) -> List[Office]:
    """
    Retrieves a list of offices with optional spatial bounding box and text search.
    """
    query = select(Office).options(selectinload(Office.address))
    if not include_inactive:
      query = query.where(Office.is_active == True)

    query = apply_search_filter(query, search, Office.name, Office.description)

    if bbox:
      query = query.join(Office.address)
      query = apply_bbox_filter(query, Address, bbox)
      
    query = query.order_by(Office.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


  @staticmethod
  def add(db: AsyncSession, office: Office) -> None:
    db.add(office)


  @staticmethod
  def add_history(db: AsyncSession, history_entry: OfficeHistory) -> None:
    db.add(history_entry)