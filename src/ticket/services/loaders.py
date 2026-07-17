"""Canonical entity loaders used by ticket application services."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundException
from src.ticket.models import Ticket, TicketWorkItem
from src.ticket.repository import TicketRepository


async def require_ticket(
  db: AsyncSession,
  ticket_id: uuid.UUID,
  *,
  for_update: bool = False,
) -> Ticket:
  """Loads one ticket or raises the canonical ticket-not-found error."""

  ticket = (
    await TicketRepository.get_by_id_for_update(db, ticket_id)
    if for_update
    else await TicketRepository.get_by_id(db, ticket_id)
  )
  if ticket is None:
    raise ResourceNotFoundException(
      "Ticket not found",
      error_code="TICKET_NOT_FOUND",
    )
  return ticket


async def require_work_item_for_update(
  db: AsyncSession,
  work_item_id: uuid.UUID,
) -> TicketWorkItem:
  """Locks one work item or raises the canonical work-item-not-found error."""

  work_item = await TicketRepository.get_work_item_for_update(db, work_item_id)
  if work_item is None:
    raise ResourceNotFoundException(
      "Work item not found",
      error_code="TICKET_WORK_ITEM_NOT_FOUND",
    )
  return work_item
