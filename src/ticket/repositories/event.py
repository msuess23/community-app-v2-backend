"""Queries for append-only ticket event streams."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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
      .where(TicketEvent.ticket_id == ticket_id)
      .order_by(TicketEvent.sequence_number.asc())
    )
    return list(result.scalars().all())

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
      .where(
        TicketEvent.ticket_id == ticket_id,
        TicketEvent.event_type == TicketEventType.TICKET_COMMENTED,
      )
      .order_by(TicketEvent.sequence_number.asc())
    )
    return list(result.scalars().all())
