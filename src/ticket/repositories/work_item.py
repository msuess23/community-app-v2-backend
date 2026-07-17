"""Queries for projected parallel ticket work items."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.ticket.events import (
  TicketWorkItemStatus,
)
from src.ticket.models import TicketWorkItem

class TicketWorkItemRepository:
  """Persists and queries workflow task projections."""

  @staticmethod
  def add_work_item(db: AsyncSession, work_item: TicketWorkItem) -> None:
    """Stages a projected parallel workflow task."""

    db.add(work_item)

  @staticmethod
  async def get_work_items(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> list[TicketWorkItem]:
    """Returns projected tasks in creation order for an internal detail view."""

    result = await db.execute(
      select(TicketWorkItem)
      .where(TicketWorkItem.ticket_id == ticket_id)
      .order_by(TicketWorkItem.created_at.asc(), TicketWorkItem.id.asc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_work_item_for_update(
    db: AsyncSession,
    work_item_id: uuid.UUID,
  ) -> TicketWorkItem | None:
    """Locks one work item while its completion event is appended."""

    result = await db.execute(
      select(TicketWorkItem)
      .where(TicketWorkItem.id == work_item_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_open_work_item_ids_for_user(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    user_id: uuid.UUID,
  ) -> list[uuid.UUID]:
    """Returns task IDs that the given user may complete on this ticket."""

    result = await db.execute(
      select(TicketWorkItem.id)
      .where(
        TicketWorkItem.ticket_id == ticket_id,
        TicketWorkItem.assignee_user_id == user_id,
        TicketWorkItem.status == TicketWorkItemStatus.OPEN,
      )
      .order_by(TicketWorkItem.created_at.asc(), TicketWorkItem.id.asc())
    )
    return list(result.scalars().all())

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

  @staticmethod
  async def has_open_blocking_work_items(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> bool:
    """Checks whether a parallel round still contains unfinished blockers."""

    result = await db.execute(
      select(TicketWorkItem.id)
      .where(
        TicketWorkItem.ticket_id == ticket_id,
        TicketWorkItem.status == TicketWorkItemStatus.OPEN,
        TicketWorkItem.is_blocking.is_(True),
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None

  @staticmethod
  async def get_open_requested_work_item_ids(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    requested_by_user_id: uuid.UUID,
  ) -> list[uuid.UUID]:
    """Returns open task IDs that the given coordinator originally requested."""

    result = await db.execute(
      select(TicketWorkItem.id)
      .where(
        TicketWorkItem.ticket_id == ticket_id,
        TicketWorkItem.requested_by_user_id == requested_by_user_id,
        TicketWorkItem.status == TicketWorkItemStatus.OPEN,
      )
      .order_by(TicketWorkItem.created_at.asc(), TicketWorkItem.id.asc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def has_open_work_items(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> bool:
    """Checks whether any projected workflow task remains unfinished."""

    result = await db.execute(
      select(TicketWorkItem.id)
      .where(
        TicketWorkItem.ticket_id == ticket_id,
        TicketWorkItem.status == TicketWorkItemStatus.OPEN,
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None
