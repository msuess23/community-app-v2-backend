import uuid
from datetime import datetime
from typing import Any, ClassVar, Mapping

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from src.address.models import Address
from src.core.filters import (
  LifecycleStatusFilter,
  SortOrder,
  apply_bbox_filter,
  apply_lifecycle_filter,
  apply_search_filter,
)
from src.core.pagination import execute_page
from src.office.models import Office, OfficeHistory, OfficeSortField


class OfficeRepository:
  """Data access layer for Office and OfficeHistory entities."""

  SORT_COLUMNS: ClassVar[Mapping[OfficeSortField, InstrumentedAttribute[Any]]] = {
    OfficeSortField.CREATED_AT: Office.created_at,
    OfficeSortField.NAME: Office.name,
    OfficeSortField.CONTACT_EMAIL: Office.contact_email,
  }

  @staticmethod
  async def get_by_id(db: AsyncSession, office_id: uuid.UUID) -> Office | None:
    """Load one office and its owned address by identifier."""

    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(Office.id == office_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_name(db: AsyncSession, name: str) -> Office | None:
    """Returns the first match; office names are intentionally not unique."""
    result = await db.execute(
      select(Office)
      .options(selectinload(Office.address))
      .where(func.lower(Office.name) == name.strip().lower())
      .order_by(Office.created_at, Office.id)
      .limit(1)
    )
    return result.scalars().first()

  @staticmethod
  async def get_page(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    sort_by: OfficeSortField = OfficeSortField.NAME,
    order: SortOrder = SortOrder.ASC,
  ) -> tuple[list[Office], int]:
    """Return a filtered, sorted, and paginated page of offices."""

    query = select(Office).options(selectinload(Office.address))
    query = apply_lifecycle_filter(query, Office, status)
    query = apply_search_filter(
      query,
      search,
      Office.name,
      Office.description,
      Office.contact_email,
    )

    if bbox:
      query = query.join(Office.address)
      query = apply_bbox_filter(query, Address, bbox)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=OfficeRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Office.id,
      unique=True,
    )

  @staticmethod
  def add(db: AsyncSession, office: Office) -> None:
    """Stage a new office row in the current transaction."""

    db.add(office)

  @staticmethod
  def add_history(db: AsyncSession, history_entry: OfficeHistory) -> None:
    """Stage an immutable office history snapshot."""

    db.add(history_entry)

  @staticmethod
  async def get_history_page(
    db: AsyncSession,
    office_id: uuid.UUID,
    *,
    page: int,
    size: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
  ) -> tuple[list[OfficeHistory], int]:
    """Return a paginated office history timeline."""

    query = select(OfficeHistory).where(OfficeHistory.office_id == office_id)

    if start_date:
      query = query.where(OfficeHistory.changed_at >= start_date)
    if end_date:
      query = query.where(OfficeHistory.changed_at <= end_date)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=OfficeHistory.changed_at,
      order=SortOrder.DESC,
      tie_breaker=OfficeHistory.id,
    )
