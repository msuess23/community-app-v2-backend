"""Queries for community ticket votes."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.ticket.models import TicketVote

class TicketVoteRepository:
  """Persists and queries community votes."""

  @staticmethod
  def add_vote(db: AsyncSession, vote: TicketVote) -> None:
    """Stages one unique community vote for insertion."""

    db.add(vote)

  @staticmethod
  async def get_vote(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
  ) -> TicketVote | None:
    """Returns the caller's vote for one ticket, if present."""

    result = await db.execute(
      select(TicketVote).where(
        TicketVote.ticket_id == ticket_id,
        TicketVote.user_id == user_id,
      )
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def count_votes(db: AsyncSession, ticket_id: uuid.UUID) -> int:
    """Counts all current community votes for one ticket."""

    result = await db.execute(
      select(func.count(TicketVote.id)).where(TicketVote.ticket_id == ticket_id)
    )
    return int(result.scalar_one())
