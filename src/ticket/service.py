"""Compatibility facade for citizen ticket commands, queries and event helpers."""

from src.ticket.services import (
  TicketAccessPolicy, TicketCommandService, TicketEventStore, TicketQueryService,
  TicketResponseMapper,
)


class TicketService(TicketCommandService, TicketQueryService):
  """Preserves the original service API while delegating focused concerns."""

  _address_snapshot = staticmethod(TicketEventStore._address_snapshot)
  _state_from_ticket = staticmethod(TicketEventStore._state_from_ticket)
  _sync_projection = staticmethod(TicketEventStore._sync_projection)
  _build_event = staticmethod(TicketEventStore._build_event)
  _append_event = staticmethod(TicketEventStore._append_event)
  _can_view_ticket = staticmethod(TicketAccessPolicy.can_view)
  _status_response = staticmethod(TicketResponseMapper.to_status)
  _ticket_response = staticmethod(TicketResponseMapper.to_public_ticket)
  rebuild_from_event_stream = staticmethod(TicketEventStore.rebuild_from_event_stream)
  projection_matches_event_stream = staticmethod(TicketEventStore.projection_matches_event_stream)
