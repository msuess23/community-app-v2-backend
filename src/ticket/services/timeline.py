"""Helpers that derive citizen-visible status entries from internal events."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from src.ticket.models import TicketEvent
from src.ticket.schemas import TicketStatusResponse
from src.ticket.services.mapper import TicketResponseMapper


def status_history(events: list[TicketEvent]) -> list[TicketStatusResponse]:
  """Map ordered events to the reduced citizen-facing status history."""

  return [
    status
    for event in events
    if (status := TicketResponseMapper.to_status(event)) is not None
  ]


def latest_status_events(
  events: list[TicketEvent],
) -> dict[UUID, TicketEvent]:
  """Return the latest event producing a citizen status for each ticket."""

  grouped: dict[UUID, list[TicketEvent]] = defaultdict(list)
  for event in events:
    grouped[event.ticket_id].append(event)

  latest: dict[UUID, TicketEvent] = {}
  for ticket_id, ticket_events in grouped.items():
    for event in reversed(ticket_events):
      if TicketResponseMapper.to_status(event) is not None:
        latest[ticket_id] = event
        break
  return latest
