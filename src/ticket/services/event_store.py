"""Ticket-specific event persistence, projection synchronization and replay."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address
from src.address.schemas import AddressCreate
from src.core.exceptions import ResourceNotFoundException
from src.ticket.events import (
  AddressSnapshot, TicketAggregateState, TicketCommentedPayload, TicketEventType, TicketStatus,
  evolve_ticket, rebuild_ticket,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.repository import TicketRepository

class TicketEventStore:
  """Keeps the append-only event stream and ticket projection consistent."""

  @staticmethod
  def _address_snapshot(address: Address | AddressCreate | None) -> AddressSnapshot | None:
    """Converts an address entity or request into an immutable event value."""

    if address is None:
      return None
    return AddressSnapshot(
      street=address.street,
      house_number=address.house_number,
      zip_code=address.zip_code,
      city=address.city,
      latitude=address.latitude,
      longitude=address.longitude,
    )

  @staticmethod
  def _state_from_ticket(ticket: Ticket) -> TicketAggregateState:
    """Maps the current SQLAlchemy projection back to pure aggregate state."""

    return TicketAggregateState(
      title=ticket.title,
      description=ticket.description,
      category=ticket.category,
      creator_user_id=ticket.creator_user_id,
      office_id=ticket.office_id,
      address=TicketEventStore._address_snapshot(ticket.address),
      visibility=ticket.visibility,
      public_status=ticket.public_status,
      public_status_message=ticket.public_status_message,
      workflow_state=ticket.workflow_state,
      primary_officer_id=ticket.primary_officer_id,
      current_responsible_user_id=ticket.current_responsible_user_id,
      pending_return_to_user_id=ticket.pending_return_to_user_id,
      version=ticket.version,
      created_at=ticket.created_at,
      updated_at=ticket.updated_at,
      resolved_at=ticket.resolved_at,
      cancelled_at=ticket.cancelled_at,
    )

  @staticmethod
  def _sync_projection(ticket: Ticket, state: TicketAggregateState) -> None:
    """Copies aggregate scalar values to the query-oriented read model."""

    ticket.title = state.title
    ticket.description = state.description
    ticket.category = state.category
    ticket.office_id = state.office_id
    ticket.visibility = state.visibility
    ticket.public_status = state.public_status
    ticket.public_status_message = state.public_status_message
    ticket.workflow_state = state.workflow_state
    ticket.primary_officer_id = state.primary_officer_id
    ticket.current_responsible_user_id = state.current_responsible_user_id
    ticket.pending_return_to_user_id = state.pending_return_to_user_id
    ticket.version = state.version
    ticket.created_at = state.created_at
    ticket.updated_at = state.updated_at
    ticket.resolved_at = state.resolved_at
    ticket.cancelled_at = state.cancelled_at

  @staticmethod
  def _event_visibility(
    event_type: TicketEventType,
    state: TicketAggregateState,
    payload,
  ) -> tuple[bool, TicketStatus | None, str | None]:
    """Defines which workflow changes become part of the citizen timeline."""

    if event_type in {
      TicketEventType.TICKET_SUBMITTED,
      TicketEventType.TICKET_DISPATCHED,
      TicketEventType.CITIZEN_RESPONSE_REQUESTED,
      TicketEventType.CITIZEN_RESPONDED,
      TicketEventType.ESCALATION_APPROVED,
      TicketEventType.TICKET_RESOLVED,
      TicketEventType.TICKET_REJECTED,
      TicketEventType.TICKET_CANCELLED,
    }:
      return True, state.public_status, state.public_status_message
    if event_type == TicketEventType.TICKET_DETAILS_UPDATED:
      return True, None, None
    if event_type == TicketEventType.TICKET_COMMENTED:
      comment = payload
      assert isinstance(comment, TicketCommentedPayload)
      return not comment.is_internal, None, None
    return False, None, None

  @staticmethod
  def _build_event(
    *,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    event_type: TicketEventType,
    payload,
    state: TicketAggregateState,
    occurred_at: datetime,
  ) -> TicketEvent:
    """Builds one append-only event after the new aggregate state is known."""

    citizen_visible, public_status, public_message = TicketEventStore._event_visibility(
      event_type,
      state,
      payload,
    )
    return TicketEvent(
      id=uuid.uuid4(),
      ticket_id=ticket_id,
      sequence_number=state.version,
      event_type=event_type,
      actor_user_id=actor_user_id,
      occurred_at=occurred_at,
      payload=payload.model_dump(mode="json", exclude_unset=True),
      citizen_visible=citizen_visible,
      public_status=public_status,
      public_message=public_message,
    )

  @staticmethod
  async def _append_event(
    db: AsyncSession,
    ticket: Ticket,
    *,
    actor_user_id: uuid.UUID,
    event_type: TicketEventType,
    payload,
    occurred_at: datetime | None = None,
  ) -> TicketEvent:
    """Atomically appends an event and updates the in-transaction projection."""

    event_time = occurred_at or datetime.now(timezone.utc)
    current_state = TicketEventStore._state_from_ticket(ticket)
    next_state = evolve_ticket(
      current_state,
      event_type,
      payload,
      occurred_at=event_time,
    )

    # The event and projection are staged in the same request transaction.  A
    # failure in either write therefore rolls both changes back together.
    TicketEventStore._sync_projection(ticket, next_state)
    event = TicketEventStore._build_event(
      ticket_id=ticket.id,
      actor_user_id=actor_user_id,
      event_type=event_type,
      payload=payload,
      state=next_state,
      occurred_at=event_time,
    )
    TicketRepository.add(db, ticket)
    TicketRepository.add_event(db, event)
    await db.flush()
    return event

  @staticmethod
  async def rebuild_from_event_stream(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> TicketAggregateState:
    """Rebuilds one ticket solely from its persisted append-only events."""

    events = await TicketRepository.get_events(db, ticket_id)
    if not events:
      raise ResourceNotFoundException(
        "Ticket not found",
        error_code="TICKET_NOT_FOUND",
      )
    return rebuild_ticket(
      [
        (event.event_type, event.payload, event.occurred_at)
        for event in events
      ]
    )

  @staticmethod
  async def projection_matches_event_stream(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> bool:
    """Compares the query projection with a deterministic event replay."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException(
        "Ticket not found",
        error_code="TICKET_NOT_FOUND",
      )
    rebuilt = await TicketEventStore.rebuild_from_event_stream(db, ticket_id)
    projected = TicketEventStore._state_from_ticket(ticket)
    return rebuilt == projected
