import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.address.models import Address
from src.core.filters import (
  BoundingBox,
  LifecycleStatusFilter,
  apply_bbox_filter,
  apply_lifecycle_filter,
  apply_search_filter,
)
from src.core.normalization import normalize_office_name
from src.core.pagination import PaginationParams, SortOrder
from src.office.models import Office, OfficeHistory
from src.office.schemas import OfficeSortField


class OfficeRepository:
  """Data access layer for offices and archived old-state snapshots."""

  @staticmethod
  async def get_by_id(db: AsyncSession, office_id: uuid.UUID) -> Optional[Office]:
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.id == office_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_active_by_id(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> Optional[Office]:
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.id == office_id, Office.is_active.is_(True))
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
  async def get_page(
    db: AsyncSession,
    *,
    pagination: PaginationParams,
    status: LifecycleStatusFilter,
    search: Optional[str],
    bbox: Optional[BoundingBox],
    sort_by: OfficeSortField,
    order: SortOrder,
  ) -> tuple[list[Office], int]:
    query = select(Office).options(selectinload(Office.address))
    query = apply_lifecycle_filter(query, Office, status)
    query = apply_search_filter(query, search, Office.name, Office.description)

    if bbox is not None:
      query = query.join(Office.address)
      query = apply_bbox_filter(query, Address, bbox)

    total_query = select(func.count()).select_from(
      query.order_by(None).options().subquery()
    )
    total = int((await db.execute(total_query)).scalar_one())

    sort_columns = {
      OfficeSortField.NAME: Office.name,
      OfficeSortField.CREATED_AT: Office.created_at,
    }
    sort_column = sort_columns[sort_by]
    sort_expression = sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
    id_tie_breaker = Office.id.asc() if order == SortOrder.ASC else Office.id.desc()

    query = (
      query.order_by(sort_expression, id_tie_breaker)
      .offset(pagination.offset)
      .limit(pagination.size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total

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
  ) -> list[OfficeHistory]:
    """Return archived states whose validity interval overlaps the range."""
    query = select(OfficeHistory).where(OfficeHistory.office_id == office_id)

    if start_date is not None:
      query = query.where(OfficeHistory.valid_to > start_date)
    if end_date is not None:
      query = query.where(OfficeHistory.valid_from <= end_date)

    query = query.order_by(
      OfficeHistory.valid_from.desc(),
      OfficeHistory.id.desc(),
    )
    result = await db.execute(query)
    return list(result.scalars().all())
