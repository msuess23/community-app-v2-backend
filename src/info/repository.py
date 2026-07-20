"""Database access for Info rows and their lightweight status history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar, Mapping

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from src.address.models import Address
from src.core.filters import SortOrder, apply_bbox_filter, apply_search_filter
from src.core.pagination import execute_page
from src.info.models import (
  Info,
  InfoCategory,
  InfoImage,
  InfoSortField,
  InfoStatus,
  InfoStatusEntry,
)


class InfoRepository:
  """Queries and persistence operations for mutable Info entities."""

  SORT_COLUMNS: ClassVar[Mapping[InfoSortField, InstrumentedAttribute[Any]]] = {
    InfoSortField.STARTS_AT: Info.starts_at,
    InfoSortField.ENDS_AT: Info.ends_at,
    InfoSortField.CREATED_AT: Info.created_at,
    InfoSortField.UPDATED_AT: Info.updated_at,
    InfoSortField.TITLE: Info.title,
  }

  @staticmethod
  def _detail_query():
    return select(Info).options(
      selectinload(Info.address),
      selectinload(Info.images),
    )

  @staticmethod
  async def get_by_id(
    db: AsyncSession,
    info_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> Info | None:
    query = InfoRepository._detail_query().where(Info.id == info_id)
    if for_update:
      query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()

  @staticmethod
  async def get_page(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    office_id: uuid.UUID | None,
    category: InfoCategory | None,
    status: InfoStatus | None,
    starts_from: datetime | None,
    ends_to: datetime | None,
    search: str | None,
    bbox: tuple[float, float, float, float] | None,
    sort_by: InfoSortField,
    order: SortOrder,
  ) -> tuple[list[Info], int]:
    query = InfoRepository._detail_query()
    query = apply_search_filter(query, search, Info.title, Info.description)

    if office_id is not None:
      query = query.where(Info.office_id == office_id)
    if category is not None:
      query = query.where(Info.category == category)
    if status is not None:
      query = query.where(Info.current_status == status)
    if starts_from is not None:
      query = query.where(Info.starts_at >= starts_from)
    if ends_to is not None:
      query = query.where(Info.ends_at <= ends_to)
    if bbox is not None:
      query = query.outerjoin(Address, Info.address_id == Address.id)
      query = apply_bbox_filter(query, Address, bbox)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=InfoRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Info.id,
    )

  @staticmethod
  def add(db: AsyncSession, info: Info) -> None:
    db.add(info)

  @staticmethod
  async def delete(db: AsyncSession, info: Info) -> None:
    await db.delete(info)


class InfoImageRepository:
  """CRUD persistence for current Info image metadata."""

  @staticmethod
  def add(db: AsyncSession, image: InfoImage) -> None:
    db.add(image)

  @staticmethod
  async def get_image(
    db: AsyncSession,
    info_id: uuid.UUID,
    image_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> InfoImage | None:
    query = select(InfoImage).where(
      InfoImage.info_id == info_id,
      InfoImage.id == image_id,
    )
    if for_update:
      query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()

  @staticmethod
  async def get_images(
    db: AsyncSession,
    info_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> list[InfoImage]:
    query = (
      select(InfoImage)
      .where(InfoImage.info_id == info_id)
      .order_by(InfoImage.uploaded_at.asc(), InfoImage.id.asc())
    )
    if for_update:
      query = query.with_for_update()
    return list((await db.execute(query)).scalars().all())

  @staticmethod
  async def delete(db: AsyncSession, image: InfoImage) -> None:
    await db.delete(image)


class InfoStatusRepository:
  """Append and read status messages owned by one Info row."""

  @staticmethod
  def add(db: AsyncSession, entry: InfoStatusEntry) -> None:
    db.add(entry)

  @staticmethod
  async def get_history(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> list[InfoStatusEntry]:
    result = await db.execute(
      select(InfoStatusEntry)
      .where(InfoStatusEntry.info_id == info_id)
      .order_by(InfoStatusEntry.created_at.desc(), InfoStatusEntry.id.desc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_latest(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> InfoStatusEntry | None:
    result = await db.execute(
      select(InfoStatusEntry)
      .where(InfoStatusEntry.info_id == info_id)
      .order_by(InfoStatusEntry.created_at.desc(), InfoStatusEntry.id.desc())
      .limit(1)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_latest_map(
    db: AsyncSession,
    info_ids: list[uuid.UUID],
  ) -> dict[uuid.UUID, InfoStatusEntry]:
    if not info_ids:
      return {}

    result = await db.execute(
      select(InfoStatusEntry)
      .where(InfoStatusEntry.info_id.in_(info_ids))
      .distinct(InfoStatusEntry.info_id)
      .order_by(
        InfoStatusEntry.info_id.asc(),
        InfoStatusEntry.created_at.desc(),
        InfoStatusEntry.id.desc(),
      )
    )
    return {entry.info_id: entry for entry in result.scalars().all()}
