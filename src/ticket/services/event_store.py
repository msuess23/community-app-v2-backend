"""Ticket-specific event persistence, projection synchronization and replay."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address
from src.address.schemas import AddressCreate
from src.core.exceptions import ResourceNotFoundException
from src.ticket.events import (
  AddressSnapshot,
  TicketAggregateState,
  TicketEventType,
  evolve_ticket,
  rebuild_ticket,
)
from src.ticket.domain.image_projection import rebuild_ticket_images
from src.ticket.models import Ticket, TicketEvent
from src.ticket.repository import TicketRepository


class TicketEventStore:
  """Keep the append-only stream and query projections consistent."""

  @staticmethod
  def _address_snapshot(address: Address | AddressCreate | None) -> AddressSnapshot | None:
    """Convert an address entity or request into an immutable event value."""

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
    """Map the SQLAlchemy projection back to pure aggregate state."""

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
      completed_at=ticket.completed_at,
      cancelled_at=ticket.cancelled_at,
    )

  @staticmethod
  def _sync_projection(ticket: Ticket, state: TicketAggregateState) -> None:
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
    ticket.current_responsible_user_id = state.current_responsible_user_id
    ticket.pending_return_to_user_id = state.pending_return_to_user_id
    ticket.version = state.version
    ticket.created_at = state.created_at
    ticket.updated_at = state.updated_at
    ticket.completed_at = state.completed_at
    ticket.cancelled_at = state.cancelled_at

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
  async def _append_event(
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
      TicketEventStore._state_from_ticket(ticket),
      event_type,
      payload,
      occurred_at=event_time,
    )

    # Event and projection are staged in the same request transaction. A
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
    """Rebuild one ticket solely from its persisted append-only events."""

    events = await TicketRepository.get_events(db, ticket_id)
    if not events:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return rebuild_ticket(
      [(event.event_type, event.payload, event.occurred_at) for event in events]
    )

  @staticmethod
  async def projection_matches_event_stream(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> bool:
    """Compare ticket and image projections with deterministic event replay."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events = await TicketRepository.get_events(db, ticket_id)
    rebuilt_ticket = rebuild_ticket(
      [(event.event_type, event.payload, event.occurred_at) for event in events]
    )
    if rebuilt_ticket != TicketEventStore._state_from_ticket(ticket):
      return False

    rebuilt_images = rebuild_ticket_images(
      [
        (
          event.id,
          event.event_type,
          event.actor_user_id,
          event.payload,
          event.occurred_at,
        )
        for event in events
      ]
    )
    projected_images = await TicketRepository.get_images(
      db,
      ticket_id,
      include_removed=True,
    )
    if set(rebuilt_images) != {image.id for image in projected_images}:
      return False
    for image in projected_images:
      if rebuilt_images[image.id].model_dump() != {
        "id": image.id,
        "storage_key": image.storage_key,
        "original_filename": image.original_filename,
        "mime_type": image.mime_type,
        "size_bytes": image.size_bytes,
        "uploaded_by_user_id": image.uploaded_by_user_id,
        "uploaded_at": image.uploaded_at,
        "is_active": image.is_active,
        "is_cover": image.is_cover,
        "removed_at": image.removed_at,
        "removed_by_user_id": image.removed_by_user_id,
        "added_event_id": image.added_event_id,
        "removed_event_id": image.removed_event_id,
        "cover_selected_event_id": image.cover_selected_event_id,
      }:
        return False
    return True
