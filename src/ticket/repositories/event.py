"""Queries for append-only ticket event streams."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.core.filters import SortOrder
from src.core.pagination import execute_page
from src.ticket.domain import TicketEventType
from src.ticket.models import TicketEvent


class TicketEventRepository:
  """Persist and read ordered ticket events."""

  @staticmethod
  def add_event(db: AsyncSession, event: TicketEvent) -> None:
    """Stage one immutable event in the aggregate stream."""

    db.add(event)

  @staticmethod
  async def get_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> list[TicketEvent]:
    """Return one event stream ordered by aggregate sequence number."""

    result = await db.execute(
      select(TicketEvent)
      .options(selectinload(TicketEvent.actor))
      .where(TicketEvent.ticket_id == ticket_id)
      .order_by(TicketEvent.sequence_number.asc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_event_page(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    *,
    page: int,
    size: int,
  ) -> tuple[list[TicketEvent], int]:
    """Return one event page with the newest aggregate changes first."""

    query = (
      select(TicketEvent)
      .options(selectinload(TicketEvent.actor))
      .where(TicketEvent.ticket_id == ticket_id)
    )
    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=TicketEvent.sequence_number,
      order=SortOrder.DESC,
      tie_breaker=TicketEvent.id,
    )

  @staticmethod
  async def get_events_for_tickets(
    db: AsyncSession,
    ticket_ids: list[uuid.UUID],
  ) -> list[TicketEvent]:
    """Load ordered events used to derive citizen timelines for ticket pages."""

    if not ticket_ids:
      return []
    result = await db.execute(
      select(TicketEvent)
      .options(selectinload(TicketEvent.actor))
      .where(TicketEvent.ticket_id.in_(ticket_ids))
      .order_by(TicketEvent.ticket_id.asc(), TicketEvent.sequence_number.asc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_comment_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> list[TicketEvent]:
    """Return append-only ticket comments in aggregate order."""

    result = await db.execute(
      select(TicketEvent)
      .options(selectinload(TicketEvent.actor))
      .where(
        TicketEvent.ticket_id == ticket_id,
        TicketEvent.event_type == TicketEventType.TICKET_COMMENTED,
      )
      .order_by(TicketEvent.sequence_number.asc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_last_sequence_number(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> int:
    """Return the persisted stream version for projection verification."""

    result = await db.execute(
      select(func.coalesce(func.max(TicketEvent.sequence_number), 0)).where(
        TicketEvent.ticket_id == ticket_id
      )
    )
    return int(result.scalar_one())

