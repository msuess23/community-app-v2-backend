"""Database queries for ticket projections and event streams."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.address.models import Address
from src.core.filters import SortOrder, apply_bbox_filter, apply_search_filter
from src.ticket.events import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkItemStatus,
)
from src.ticket.models import Ticket, TicketEvent, TicketSortField, TicketWorkItem


class TicketRepository:
  """Data access layer for the ticket read model and append-only events."""

  SORT_COLUMNS = {
    TicketSortField.CREATED_AT: Ticket.created_at,
    TicketSortField.UPDATED_AT: Ticket.updated_at,
    TicketSortField.TITLE: Ticket.title,
    TicketSortField.STATUS: Ticket.public_status,
  }

  @staticmethod
  def add(db: AsyncSession, ticket: Ticket) -> None:
    """Stages a ticket projection for insertion or update."""

    db.add(ticket)

  @staticmethod
  def add_event(db: AsyncSession, event: TicketEvent) -> None:
    """Stages one immutable event in the aggregate stream."""

    db.add(event)

  @staticmethod
  def add_work_item(db: AsyncSession, work_item: TicketWorkItem) -> None:
    """Stages a projected parallel workflow task."""

    db.add(work_item)

  @staticmethod
  async def get_by_id(db: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    """Loads a ticket and its owned address without acquiring a row lock."""

    result = await db.execute(
      select(Ticket)
      .options(selectinload(Ticket.address))
      .where(Ticket.id == ticket_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id_for_update(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> Ticket | None:
    """Locks the projection while a new event and state update are appended."""

    result = await db.execute(
      select(Ticket)
      .options(selectinload(Ticket.address))
      .where(Ticket.id == ticket_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_public_page(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    office_id: uuid.UUID | None = None,
    category: TicketCategory | None = None,
    status: TicketStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> tuple[list[Ticket], int]:
    """Returns public community tickets using the former Ktor filter meanings."""

    query = (
      select(Ticket)
      .options(selectinload(Ticket.address))
      .where(Ticket.visibility == TicketVisibility.PUBLIC)
    )
    query = apply_search_filter(query, search, Ticket.title, Ticket.description)

    if office_id is not None:
      query = query.where(Ticket.office_id == office_id)
    if category is not None:
      query = query.where(Ticket.category == category)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if created_from is not None:
      query = query.where(Ticket.created_at >= created_from)
    if created_to is not None:
      query = query.where(Ticket.created_at <= created_to)
    if bbox is not None:
      query = query.outerjoin(Address, Ticket.address_id == Address.id)
      query = apply_bbox_filter(query, Address, bbox)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())

    sort_column = TicketRepository.SORT_COLUMNS[sort_by]
    ordering = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
    query = query.order_by(ordering, Ticket.id.asc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    return list(result.scalars().unique().all()), total

  @staticmethod
  async def get_creator_page(
    db: AsyncSession,
    *,
    creator_user_id: uuid.UUID,
    page: int,
    size: int,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> tuple[list[Ticket], int]:
    """Returns every public or private ticket created by one citizen."""

    query = (
      select(Ticket)
      .options(selectinload(Ticket.address))
      .where(Ticket.creator_user_id == creator_user_id)
    )
    query = apply_search_filter(query, search, Ticket.title, Ticket.description)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if category is not None:
      query = query.where(Ticket.category == category)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())

    sort_column = TicketRepository.SORT_COLUMNS[sort_by]
    ordering = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
    query = query.order_by(ordering, Ticket.id.asc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    return list(result.scalars().unique().all()), total

  @staticmethod
  async def get_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    *,
    citizen_visible_only: bool = False,
  ) -> list[TicketEvent]:
    """Returns an event stream ordered by its aggregate sequence number."""

    query = select(TicketEvent).where(TicketEvent.ticket_id == ticket_id)
    if citizen_visible_only:
      query = query.where(TicketEvent.citizen_visible.is_(True))
    result = await db.execute(query.order_by(TicketEvent.sequence_number.asc()))
    return list(result.scalars().all())

  @staticmethod
  async def get_latest_public_events(
    db: AsyncSession,
    ticket_ids: list[uuid.UUID],
  ) -> dict[uuid.UUID, TicketEvent]:
    """Loads the latest public-status event for every requested ticket."""

    if not ticket_ids:
      return {}

    latest_sequence = (
      select(
        TicketEvent.ticket_id.label("ticket_id"),
        func.max(TicketEvent.sequence_number).label("sequence_number"),
      )
      .where(
        TicketEvent.ticket_id.in_(ticket_ids),
        TicketEvent.citizen_visible.is_(True),
        TicketEvent.public_status.is_not(None),
      )
      .group_by(TicketEvent.ticket_id)
      .subquery()
    )
    result = await db.execute(
      select(TicketEvent).join(
        latest_sequence,
        and_(
          TicketEvent.ticket_id == latest_sequence.c.ticket_id,
          TicketEvent.sequence_number == latest_sequence.c.sequence_number,
        ),
      )
    )
    return {event.ticket_id: event for event in result.scalars().all()}

  @staticmethod
  async def has_open_work_item_for_user(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
  ) -> bool:
    """Checks whether a staff member owns an active parallel subtask."""

    result = await db.execute(
      select(TicketWorkItem.id)
      .where(
        TicketWorkItem.ticket_id == ticket_id,
        TicketWorkItem.assignee_user_id == user_id,
        TicketWorkItem.status == TicketWorkItemStatus.OPEN,
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None
