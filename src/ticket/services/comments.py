"""Append-only comment commands and queries for tickets."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
  ForbiddenException,
  ResourceNotFoundException,
)
from src.ticket.domain import TicketCommentedPayload, TicketEventType, TicketWorkflowState
from src.ticket.models import TicketEvent
from src.ticket.repositories.event import TicketEventRepository
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.schemas import (
  TicketCommentAuthorResponse,
  TicketCommentCreateRequest,
  TicketCommentResponse,
)
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.errors import TicketActionNotAllowedException
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.mapper import TicketReferenceMapper
from src.ticket.services.loaders import require_ticket
from src.user.models import Role, User
from src.user.roles import AUTHORITY_ROLES


class TicketCommentService:
  """Stores comments as events and filters internal notes for citizen clients."""

  @staticmethod
  def _response(
    event: TicketEvent,
    *,
    author: User | None = None,
    expose_identity: bool = True,
  ) -> TicketCommentResponse:
    """Converts a validated comment event to the API response model."""

    payload = TicketCommentedPayload.model_validate(event.payload)
    author_user = author or event.actor
    author_type = (
      "CITIZEN"
      if author_user is not None and author_user.role == Role.CITIZEN
      else "AUTHORITY"
    )
    identity = TicketReferenceMapper.user_or_fallback(
      author_user,
      event.actor_user_id,
    )
    author_reference = TicketCommentAuthorResponse(
      id=identity.id if expose_identity else None,
      display_name=(
        identity.display_name
        if expose_identity
        else "Citizen" if author_type == "CITIZEN" else "Authority employee"
      ),
      author_type=author_type,
    )
    return TicketCommentResponse(
      id=event.id,
      ticket_id=event.ticket_id,
      text=payload.text,
      is_internal=payload.is_internal,
      created_at=event.occurred_at,
      author=author_reference,
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
        raise TicketActionNotAllowedException(
          "A completed ticket no longer accepts citizen comments."
        )
    elif current_user.role in AUTHORITY_ROLES:
      if not TicketAccessPolicy.can_view_internal(ticket, current_user):
        raise ResourceNotFoundException(
          "Ticket not found",
          error_code="TICKET_NOT_FOUND",
        )
    else:
      raise ForbiddenException("This account cannot comment on tickets")

    event = await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_COMMENTED,
      payload=TicketCommentedPayload(
        text=request.text,
        is_internal=request.is_internal,
      ),
    )
    return TicketCommentService._response(event, author=current_user)

  @staticmethod
  async def list_comments(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> list[TicketCommentResponse]:
    """Returns all comments visible to the requesting public or staff client."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")

    include_internal = False
    if current_user is not None and current_user.role in AUTHORITY_ROLES:
      include_internal = TicketAccessPolicy.can_view_internal(ticket, current_user)

    # A signed-in staff user without internal access retains the same public
    # visibility as an anonymous caller, but never receives internal notes.
    if not include_internal and not TicketAccessPolicy.can_view(
      ticket, current_user
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")

    events = await TicketEventRepository.get_comment_events(db, ticket.id)
    responses = [
      TicketCommentService._response(
        event,
        expose_identity=include_internal,
      )
      for event in events
    ]
    if include_internal:
      return responses
    return [comment for comment in responses if not comment.is_internal]
