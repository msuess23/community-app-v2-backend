"""Citizen commands that create or mutate the ticket aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.service import AddressService
from src.core.exceptions import ConflictException, ForbiddenException, WorkflowValidationException
from src.ticket.events import (
  TicketCancelledPayload, TicketDetailsUpdatedPayload, TicketEventType, TicketSubmittedPayload, TicketWorkflowState, evolve_ticket,
)
from src.ticket.models import Ticket
from src.ticket.repository import TicketRepository
from src.ticket.schemas import TicketCancelRequest, TicketCreateRequest, TicketResponse, TicketUpdateRequest
from src.user.models import Role, User

from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.ticket.services.mapper import TicketResponseMapper


class TicketCommandService:
  """Coordinates citizen ticket commands within the request transaction."""

  @staticmethod
  async def create_ticket(
    db: AsyncSession,
    request: TicketCreateRequest,
    current_user: User,
  ) -> TicketResponse:
    """Creates a central-inbox ticket from one citizen submission event."""

    if current_user.role != Role.CITIZEN:
      raise ForbiddenException("Only citizens may submit tickets")

    occurred_at = datetime.now(timezone.utc)
    payload = TicketSubmittedPayload(
      title=request.title,
      description=request.description,
      category=request.category,
      creator_user_id=current_user.id,
      address=(
        TicketEventStore._address_snapshot(request.address)
        if request.address is not None
        else None
      ),
      visibility=request.visibility,
    )
    state = evolve_ticket(
      None,
      TicketEventType.TICKET_SUBMITTED,
      payload,
      occurred_at=occurred_at,
    )

    ticket = Ticket(id=uuid.uuid4(), creator_user_id=current_user.id)
    TicketEventStore._sync_projection(ticket, state)
    if request.address is not None:
      ticket.address = AddressService.create_address_entity(request.address)

    event = TicketEventStore._build_event(
      ticket_id=ticket.id,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_SUBMITTED,
      payload=payload,
      state=state,
      occurred_at=occurred_at,
    )
    TicketRepository.add(db, ticket)
    TicketRepository.add_event(db, event)
    await db.flush()
    return TicketResponseMapper.to_public_ticket(
      ticket,
      current_status_event=event,
      current_user=current_user,
    )

  @staticmethod
  async def update_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketUpdateRequest,
    current_user: User,
  ) -> TicketResponse:
    """Appends a details event while a citizen ticket is still undispatched."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if current_user.id != ticket.creator_user_id:
      raise ForbiddenException("Only the ticket creator may edit this ticket")
    if ticket.workflow_state != TicketWorkflowState.NEW:
      raise WorkflowValidationException(
        "A ticket can only be edited before it is dispatched."
      )

    changes = request.model_dump(exclude_unset=True)
    if not changes:
      latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
      return TicketResponseMapper.to_public_ticket(
        ticket,
        current_status_event=latest.get(ticket.id),
        current_user=current_user,
      )

    if "address" in request.model_fields_set:
      address_request = request.address
      old_address = ticket.address
      ticket.address = (
        AddressService.create_address_entity(address_request)
        if address_request is not None
        else None
      )
      # delete-orphan removes the old address after the relationship is replaced.
      if old_address is not None and ticket.address is None:
        await db.flush()

    payload_values = dict(changes)
    if "address" in request.model_fields_set:
      payload_values["address"] = (
        TicketEventStore._address_snapshot(request.address)
        if request.address is not None
        else None
      )
    payload = TicketDetailsUpdatedPayload.model_validate(payload_values)
    event = await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_DETAILS_UPDATED,
      payload=payload,
    )
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketResponseMapper.to_public_ticket(
      ticket,
      current_status_event=latest.get(ticket.id) or event,
      current_user=current_user,
    )

  @staticmethod
  async def cancel_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketCancelRequest,
    current_user: User,
  ) -> None:
    """Cancels a ticket only while it is still waiting in the central inbox."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if current_user.id != ticket.creator_user_id:
      raise ForbiddenException("Only the ticket creator may cancel this ticket")
    if ticket.workflow_state != TicketWorkflowState.NEW:
      raise ConflictException(
        "A dispatched ticket can no longer be cancelled by the citizen.",
        error_code="TICKET_ALREADY_IN_PROCESS",
      )

    await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_CANCELLED,
      payload=TicketCancelledPayload(reason=request.reason),
    )
