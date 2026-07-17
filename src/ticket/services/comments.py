"""Append-only comment commands and queries for tickets."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
  ForbiddenException,
  ResourceNotFoundException,
  WorkflowValidationException,
)
from src.ticket.events import TicketCommentedPayload, TicketEventType, TicketWorkflowState
from src.ticket.models import TicketEvent
from src.ticket.repository import TicketRepository
from src.ticket.schemas import TicketCommentCreateRequest, TicketCommentResponse
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.user.models import Role, User


class TicketCommentService:
  """Stores comments as events and filters internal notes for citizen clients."""

  @staticmethod
  def _response(event: TicketEvent) -> TicketCommentResponse:
    """Converts a validated comment event to the API response model."""

    payload = TicketCommentedPayload.model_validate(event.payload)
    return TicketCommentResponse(
      id=event.id,
      ticket_id=event.ticket_id,
      text=payload.text,
      is_internal=payload.is_internal,
      author_user_id=event.actor_user_id,
      created_at=event.occurred_at,
    )

  @staticmethod
  async def add_comment(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketCommentCreateRequest,
    current_user: User,
  ) -> TicketCommentResponse:
    """Appends one immutable internal or citizen-visible comment event."""

    ticket = await require_ticket(db, ticket_id, for_update=True)

    if current_user.role == Role.CITIZEN:
      if ticket.creator_user_id != current_user.id:
        raise ForbiddenException("Citizens may only comment on their own tickets")
      if request.is_internal:
        raise ForbiddenException("Citizens cannot create internal comments")
      if ticket.workflow_state == TicketWorkflowState.COMPLETED:
        raise WorkflowValidationException("A completed ticket no longer accepts comments.")
    elif current_user.role in {Role.DISPATCHER, Role.OFFICER, Role.MANAGER}:
      if not await TicketAccessPolicy.can_view_internal(
        db,
        ticket,
        current_user,
      ):
        raise ResourceNotFoundException(
          "Ticket not found",
          error_code="TICKET_NOT_FOUND",
        )
    else:
      raise ForbiddenException("This account cannot comment on tickets")

    event = await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_COMMENTED,
      payload=TicketCommentedPayload(
        text=request.text,
        is_internal=request.is_internal,
      ),
    )
    return TicketCommentService._response(event)

  @staticmethod
  async def list_comments(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> list[TicketCommentResponse]:
    """Returns all comments visible to the requesting public or staff client."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")

    include_internal = False
    if current_user is not None and current_user.role in {
      Role.DISPATCHER,
      Role.OFFICER,
      Role.MANAGER,
    }:
      include_internal = await TicketAccessPolicy.can_view_internal(
        db,
        ticket,
        current_user,
      )
      if not include_internal:
        raise ResourceNotFoundException(
          "Ticket not found",
          error_code="TICKET_NOT_FOUND",
        )
    elif not await TicketAccessPolicy.can_view(db, ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")

    events = await TicketRepository.get_comment_events(db, ticket.id)
    responses = [TicketCommentService._response(event) for event in events]
    if include_internal:
      return responses
    return [comment for comment in responses if not comment.is_internal]
