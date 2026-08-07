"""Canonical entity loaders used by ticket application services."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundException
from src.ticket.models import Ticket
from src.ticket.repositories.ticket import TicketProjectionRepository


async def require_ticket(
  db: AsyncSession,
  ticket_id: uuid.UUID,
  *,
  for_update: bool = False,
) -> Ticket:
  """Load one ticket or raise the canonical not-found error."""

  ticket = (
    await TicketProjectionRepository.get_by_id_for_update(db, ticket_id)
    if for_update
    else await TicketProjectionRepository.get_by_id(db, ticket_id)
  )
  if ticket is None:
    raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
  return ticket
