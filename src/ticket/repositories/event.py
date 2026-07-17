"""Queries for append-only ticket event streams."""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.ticket.events import (
  TicketEventType,
)
from src.ticket.models import TicketEvent

class TicketEventRepository:
  """Persists and reads ordered ticket events."""

  @staticmethod
  def add_event(db: AsyncSession, event: TicketEvent) -> None:
    """Stages one immutable event in the aggregate stream."""

    db.add(event)

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
  async def get_comment_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> list[TicketEvent]:
    """Returns append-only ticket comments in aggregate order."""

    result = await db.execute(
      select(TicketEvent)
      .where(
        TicketEvent.ticket_id == ticket_id,
        TicketEvent.event_type == TicketEventType.TICKET_COMMENTED,
      )
      .order_by(TicketEvent.sequence_number.asc())
    )
    return list(result.scalars().all())
