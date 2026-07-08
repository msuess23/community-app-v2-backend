import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.office.models import Office, OfficeHistory

class OfficeRepository:
  """
  Data access layer for Office and OfficeHistory entities.
  """

  @staticmethod
  async def get_by_id(db: AsyncSession, office_id: uuid.UUID) -> Optional[Office]:
    result = await db.execute(select(Office).where(Office.id == office_id))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_name(db: AsyncSession, name: str) -> Optional[Office]:
    result = await db.execute(select(Office).where(Office.name == name))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100, include_inactive: bool = False) -> List[Office]:
    query = select(Office)
    if not include_inactive:
      query = query.where(Office.is_active == True)
      
    query = query.order_by(Office.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

  @staticmethod
  def add(db: AsyncSession, office: Office) -> None:
    db.add(office)

  @staticmethod
  def add_history(db: AsyncSession, history_entry: OfficeHistory) -> None:
    db.add(history_entry)