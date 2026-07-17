"""Pure mapping from ticket ORM projections and events to API responses."""

from __future__ import annotations

from src.address.schemas import AddressResponse
from src.core.config import settings
from src.ticket.domain import (
  EscalationDecision,
  TicketCompletionOutcome,
  TicketEventType,
  TicketStatus,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import (
  TicketEventResponse,
  TicketInternalResponse,
  TicketResponse,
  TicketStatusResponse,
)
from src.user.models import Role, User


class TicketResponseMapper:
  """Build stable public and internal ticket responses without queries."""

  @staticmethod
  def to_status(event: TicketEvent | None) -> TicketStatusResponse | None:
    """Derive one citizen timeline entry from an internal event."""

    if event is None:
      return None

    status: TicketStatus | None = None
    message: str | None = None
    payload = event.payload

    if event.event_type == TicketEventType.TICKET_SUBMITTED:
      status, message = TicketStatus.OPEN, "Ticket submitted"
    elif event.event_type == TicketEventType.TICKET_DISPATCHED:
      status, message = TicketStatus.IN_PROGRESS, "Forwarded to the responsible office"
    elif event.event_type == TicketEventType.CITIZEN_RESPONSE_REQUESTED:
      status, message = TicketStatus.IN_PROGRESS, payload.get("question")
    elif event.event_type == TicketEventType.CITIZEN_RESPONDED:
      status, message = TicketStatus.IN_PROGRESS, "Citizen response received"
    elif event.event_type == TicketEventType.ESCALATION_DECIDED:
      if payload.get("decision") == EscalationDecision.APPROVED.value:
        status = TicketStatus.IN_PROGRESS
        message = payload.get("comment") or "Proposed measure approved"
    elif event.event_type == TicketEventType.TICKET_COMPLETED:
      outcome = TicketCompletionOutcome(payload["outcome"])
      status = TicketStatus(outcome.value)
      message = payload.get("message")
    elif event.event_type == TicketEventType.TICKET_CANCELLED:
      status, message = TicketStatus.CANCELLED, "Ticket cancelled"

    if status is None:
      return None
    return TicketStatusResponse(
      id=event.id,
      status=status,
      message=message,
      created_by_user_id=event.actor_user_id,
      created_at=event.occurred_at,
    )

  @staticmethod
  def to_public_ticket(
    ticket: Ticket,
    *,
    current_status_event: TicketEvent | None,
    current_user: User | None,
  ) -> TicketResponse:
    """Build a citizen-facing response without exposing workflow internals."""

    can_edit = (
      current_user is not None
      and current_user.id == ticket.creator_user_id
      and ticket.workflow_state == TicketWorkflowState.NEW
    )
    active_images = [
      image for image in getattr(ticket, "images", []) if image.is_active
    ]
    cover_image = next(
      (image for image in active_images if image.is_cover),
      active_images[0] if active_images else None,
    )
    can_manage_images = can_edit
    if current_user is not None and current_user.role in {Role.OFFICER, Role.MANAGER}:
      can_manage_images = (
        ticket.workflow_state != TicketWorkflowState.COMPLETED
        and (
          current_user.id in {
            ticket.primary_officer_id,
            ticket.current_assignee_id,
          }
          or (
            current_user.office_id is not None
            and current_user.office_id == ticket.office_id
          )
        )
      )

    return TicketResponse(
      id=ticket.id,
      title=ticket.title,
      description=ticket.description,
      category=ticket.category,
      office_id=ticket.office_id,
      creator_user_id=ticket.creator_user_id,
      address=(
        AddressResponse.model_validate(ticket.address)
        if ticket.address is not None
        else None
      ),
      visibility=ticket.visibility,
      created_at=ticket.created_at,
      current_status=TicketResponseMapper.to_status(current_status_event),
      image_url=(
        f"{settings.BASE_URL}/tickets/{ticket.id}/images/{cover_image.id}/content"
        if cover_image is not None
        else None
      ),
      can_edit=can_edit,
      can_manage_images=can_manage_images,
      version=ticket.version,
    )

  @staticmethod
  def to_internal_ticket(
    ticket: Ticket,
    *,
    current_status_event: TicketEvent | None,
    current_user: User,
  ) -> TicketInternalResponse:
    """Build the authority response while reusing citizen-facing fields."""

    public_response = TicketResponseMapper.to_public_ticket(
      ticket,
      current_status_event=current_status_event,
      current_user=current_user,
    )
    public_response.can_manage_images = (
      current_user.role in {Role.OFFICER, Role.MANAGER}
      and ticket.workflow_state != TicketWorkflowState.COMPLETED
    )
    return TicketInternalResponse(
      **public_response.model_dump(),
      workflow_state=ticket.workflow_state,
      primary_officer_id=ticket.primary_officer_id,
      current_assignee_id=ticket.current_assignee_id,
      return_to_user_id=ticket.return_to_user_id,
    )

  @staticmethod
  def to_event(event: TicketEvent) -> TicketEventResponse:
    """Convert one persisted event into the internal API representation."""

    return TicketEventResponse(
      id=event.id,
      ticket_id=event.ticket_id,
      sequence_number=event.sequence_number,
      event_type=event.event_type,
      actor_user_id=event.actor_user_id,
      occurred_at=event.occurred_at,
      payload=event.payload,
    )
