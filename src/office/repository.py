import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.address.models import Address
from src.core.filters import (
  LifecycleStatusFilter,
  apply_bbox_filter,
  apply_lifecycle_filter,
  apply_search_filter,
)
from src.core.normalization import normalize_office_name
from src.office.models import Office, OfficeHistory


class OfficeRepository:
  """Data access layer for offices and their temporal history."""

  @staticmethod
  async def get_by_id(db: AsyncSession, office_id: uuid.UUID) -> Optional[Office]:
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.id == office_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id_for_update(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> Optional[Office]:
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.id == office_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_name(
    db: AsyncSession,
    name: str,
    *,
    active_only: bool = True,
    exclude_id: uuid.UUID | None = None,
  ) -> Optional[Office]:
    normalized_name = normalize_office_name(name).lower()
    query = (
      select(Office)
      .options(selectinload(Office.address))
      .where(func.lower(Office.name) == normalized_name)
    )
    if active_only:
      query = query.where(Office.is_active.is_(True))
    if exclude_id is not None:
      query = query.where(Office.id != exclude_id)

    result = await db.execute(query)
    return result.scalar_one_or_none()

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

    query = query.order_by(Office.name, Office.id).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())

  @staticmethod
  def add(db: AsyncSession, office: Office) -> None:
    db.add(office)

  @staticmethod
  def add_history(db: AsyncSession, history_entry: OfficeHistory) -> None:
    db.add(history_entry)

  @staticmethod
  async def close_current_history(
    db: AsyncSession,
    office_id: uuid.UUID,
    *,
    valid_to: datetime,
  ) -> None:
    await db.execute(
      update(OfficeHistory)
      .where(
        OfficeHistory.office_id == office_id,
        OfficeHistory.valid_to.is_(None),
      )
      .values(valid_to=valid_to)
    )

  @staticmethod
  async def get_history_by_office_id(
    db: AsyncSession,
    office_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> List[OfficeHistory]:
    """Return versions whose validity interval overlaps the requested range."""
    query = select(OfficeHistory).where(OfficeHistory.office_id == office_id)

    if start_date is not None:
      query = query.where(
        (OfficeHistory.valid_to.is_(None))
        | (OfficeHistory.valid_to > start_date)
      )
    if end_date is not None:
      query = query.where(OfficeHistory.valid_from <= end_date)

    query = query.order_by(
      OfficeHistory.valid_from.desc(),
      OfficeHistory.id.desc(),
    )
    result = await db.execute(query)
    return list(result.scalars().all())
