"""Compatibility facade for the split ticket repository modules."""

from src.ticket.repositories import (
  TicketEventRepository, TicketImageRepository, TicketProjectionRepository,
  TicketVoteRepository, TicketWorkItemRepository,
)


class TicketRepository(
  TicketProjectionRepository,
  TicketEventRepository,
  TicketWorkItemRepository,
  TicketVoteRepository,
  TicketImageRepository,
):
  """Collects ticket persistence operations behind the original public API."""
