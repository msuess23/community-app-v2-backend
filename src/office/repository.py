import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.address.models import Address
from src.core.filters import (
  LifecycleStatusFilter,
  apply_bbox_filter,
  apply_lifecycle_filter,
  apply_search_filter,
)
from src.office.models import Office, OfficeHistory


class OfficeRepository:
  """Data access layer for Office and OfficeHistory entities."""

  @staticmethod
  async def get_by_id(db: AsyncSession, office_id: uuid.UUID) -> Optional[Office]:
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.id == office_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_name(db: AsyncSession, name: str) -> Optional[Office]:
    """Returns the first matching office; office names are intentionally not unique."""
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.name == name)
      .order_by(Office.created_at, Office.id)
      .limit(1)
    )
    return result.scalars().first()

  @staticmethod
  async def get_all(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
  ) -> List[Office]:
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
    end_date: Optional[datetime] = None,
  ) -> List[OfficeHistory]:
    """Retrieves stored old-state snapshots, newest first."""
    query = select(OfficeHistory).where(OfficeHistory.office_id == office_id)

    if start_date:
      query = query.where(OfficeHistory.changed_at >= start_date)
    if end_date:
      query = query.where(OfficeHistory.changed_at <= end_date)

    result = await db.execute(query.order_by(OfficeHistory.changed_at.desc()))
    return list(result.scalars().all())
