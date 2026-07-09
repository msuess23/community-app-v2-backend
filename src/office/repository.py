import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from datetime import datetime

from src.office.models import Office, OfficeHistory
from src.address.models import Address
from src.core.filters import apply_bbox_filter, apply_search_filter, apply_lifecycle_filter, LifecycleStatusFilter

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
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None
  ) -> List[Office]:
    """
    Retrieves a list of offices with optional spatial bounding box and text search.
    """
    query = select(Office).options(selectinload(Office.address))
    
    query = apply_lifecycle_filter(query, Office, status)
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


  @staticmethod
  async def get_history_by_office_id(
    db: AsyncSession, 
    office_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
    ) -> List[OfficeHistory]:
    """Retrieves the audit trail for a specific office, newest first."""
    records = []

    # Get last change that was made before the start_date as 
    # it would still be active during part of the time frame
    if start_date:
      query_before = (
        select(OfficeHistory)
        .where(OfficeHistory.office_id == office_id, OfficeHistory.changed_at < start_date)
        .order_by(OfficeHistory.changed_at.desc())
        .limit(1)
      )
      result_before = await db.execute(query_before)
      before_record = result_before.scalar_one_or_none()
      if before_record:
        records.append(before_record)

    # Get all changes within the time frame
    query_range = select(OfficeHistory).where(OfficeHistory.office_id == office_id)

    if start_date:
      query_range = query_range.where(OfficeHistory.changed_at >= start_date)
    if end_date:
      query_range = query_range.where(OfficeHistory.changed_at <= end_date)

    query_range = query_range.order_by(OfficeHistory.changed_at.desc())

    result_range = await db.execute(query_range)
    range_records = list(result_range.scalars().all())

    # Combine both
    return range_records + records