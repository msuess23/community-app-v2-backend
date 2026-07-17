"""Compatibility facade for the split ticket repository modules."""

from src.ticket.repositories import (
  TicketEventRepository,
  TicketImageRepository,
  TicketProjectionRepository,
)


class TicketRepository(
  TicketProjectionRepository,
  TicketEventRepository,
  TicketImageRepository,
):
  """Collect ticket persistence operations behind the existing import path."""
