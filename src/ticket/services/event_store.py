"""Ticket-specific event persistence, projection synchronization and replay."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address
from src.address.schemas import AddressCreate
from src.address.snapshot import AddressSnapshot
from src.core.exceptions import ResourceNotFoundException
from src.ticket.domain import (
  TicketAggregateState,
  TicketEventType,
  evolve_ticket,
  rebuild_ticket,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.repositories.event import TicketEventRepository
from src.ticket.repositories.ticket import TicketProjectionRepository


class TicketEventStore:
  """Keep the append-only stream and query projections consistent."""

  @staticmethod
  def address_snapshot(address: Address | AddressCreate | None) -> AddressSnapshot | None:
    """Convert an address entity or request into an immutable event value."""

    return AddressSnapshot.from_address(address)

  @staticmethod
  def state_from_ticket(ticket: Ticket) -> TicketAggregateState:
    """Map the SQLAlchemy projection back to pure aggregate state."""

    return TicketAggregateState(
      title=ticket.title,
      description=ticket.description,
      category=ticket.category,
      creator_user_id=ticket.creator_user_id,
      office_id=ticket.office_id,
      address=TicketEventStore.address_snapshot(ticket.address),
      visibility=ticket.visibility,
      public_status=ticket.public_status,
      public_status_message=ticket.public_status_message,
      workflow_state=ticket.workflow_state,
      primary_officer_id=ticket.primary_officer_id,
      current_assignee_id=ticket.current_assignee_id,
      return_to_user_id=ticket.return_to_user_id,
      version=ticket.version,
      created_at=ticket.created_at,
      updated_at=ticket.updated_at,
      completed_at=ticket.completed_at,
      cancelled_at=ticket.cancelled_at,
    )

  @staticmethod
  def sync_projection(ticket: Ticket, state: TicketAggregateState) -> None:
    """Copy aggregate scalar values to the query-oriented read model."""

    ticket.title = state.title
    ticket.description = state.description
    ticket.category = state.category
    ticket.office_id = state.office_id
    ticket.visibility = state.visibility
    ticket.public_status = state.public_status
    ticket.public_status_message = state.public_status_message
    ticket.workflow_state = state.workflow_state
    ticket.primary_officer_id = state.primary_officer_id
    ticket.current_assignee_id = state.current_assignee_id
    ticket.return_to_user_id = state.return_to_user_id
    ticket.version = state.version
    ticket.created_at = state.created_at
    ticket.updated_at = state.updated_at
    ticket.completed_at = state.completed_at
    ticket.cancelled_at = state.cancelled_at

  @staticmethod
  def build_event(
    *,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    event_type: TicketEventType,
    payload,
    state: TicketAggregateState,
    occurred_at: datetime,
  ) -> TicketEvent:
    """Build one immutable event after the new aggregate state is known."""

    return TicketEvent(
      id=uuid.uuid4(),
      ticket_id=ticket_id,
      sequence_number=state.version,
      event_type=event_type,
      actor_user_id=actor_user_id,
      occurred_at=occurred_at,
      payload=payload.model_dump(mode="json", exclude_unset=True),
    )

  @staticmethod
  async def append(
    db: AsyncSession,
    ticket: Ticket,
    *,
    actor_user_id: uuid.UUID,
    event_type: TicketEventType,
    payload,
    occurred_at: datetime | None = None,
  ) -> TicketEvent:
    """Atomically append an event and update the in-transaction projection."""

    event_time = occurred_at or datetime.now(timezone.utc)
    next_state = evolve_ticket(
      TicketEventStore.state_from_ticket(ticket),
      event_type,
      payload,
      occurred_at=event_time,
    )

    # Event and projection are staged in the same request transaction. A
    # failure in either write therefore rolls both changes back together.
    TicketEventStore.sync_projection(ticket, next_state)
    event = TicketEventStore.build_event(
      ticket_id=ticket.id,
      actor_user_id=actor_user_id,
      event_type=event_type,
      payload=payload,
      state=next_state,
      occurred_at=event_time,
    )
    TicketProjectionRepository.add(db, ticket)
    TicketEventRepository.add_event(db, event)
    await db.flush()
    return event

  @staticmethod
  async def rebuild(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> TicketAggregateState:
    """Rebuild one ticket solely from its persisted append-only events."""

    events = await TicketEventRepository.get_events(db, ticket_id)
    if not events:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return rebuild_ticket(
      [(event.event_type, event.payload, event.occurred_at) for event in events]
    )
