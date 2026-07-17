"""Pure mapping from ticket ORM projections and events to API responses."""

from __future__ import annotations



from src.address.schemas import AddressResponse
from src.core.config import settings
from src.ticket.events import (
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent, TicketWorkItem
from src.ticket.schemas import (
  TicketEventResponse, TicketInternalResponse, TicketResponse, TicketStatusResponse,
  TicketWorkItemResponse,
)
from src.user.models import Role, User

class TicketResponseMapper:
  """Builds stable citizen-facing responses without executing queries."""

  @staticmethod
  def to_status(event: TicketEvent | None) -> TicketStatusResponse | None:
    """Converts a public event into the former Ktor status DTO shape."""

    if event is None or event.public_status is None:
      return None
    return TicketStatusResponse(
      id=event.id,
      status=event.public_status,
      message=event.public_message,
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
    """Builds a stable citizen-facing response without leaking workflow tasks."""

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
    votes = list(getattr(ticket, "votes", []))
    can_manage_images = can_edit
    if current_user is not None and current_user.role in {Role.OFFICER, Role.MANAGER}:
      can_manage_images = (
        ticket.workflow_state != TicketWorkflowState.COMPLETED
        and (
          current_user.id in {
            ticket.primary_officer_id,
            ticket.current_responsible_user_id,
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
      votes_count=len(votes),
      user_voted=(
        any(vote.user_id == current_user.id for vote in votes)
        if current_user is not None
        else None
      ),
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
    """Builds the staff response while reusing the citizen DTO fields."""

    public_response = TicketResponseMapper.to_public_ticket(
      ticket,
      current_status_event=current_status_event,
      current_user=current_user,
    )
    # Every officer or manager who passed the internal visibility check may add
    # revisioned evidence while the administrative workflow is still active.
    public_response.can_manage_images = (
      current_user.role in {Role.OFFICER, Role.MANAGER}
      and ticket.workflow_state != TicketWorkflowState.COMPLETED
    )
    return TicketInternalResponse(
      **public_response.model_dump(),
      workflow_state=ticket.workflow_state,
      primary_officer_id=ticket.primary_officer_id,
      current_responsible_user_id=ticket.current_responsible_user_id,
      pending_return_to_user_id=ticket.pending_return_to_user_id,
    )

  @staticmethod
  def to_event(event: TicketEvent) -> TicketEventResponse:
    """Converts one persisted event into the internal API representation."""

    return TicketEventResponse(
      id=event.id,
      ticket_id=event.ticket_id,
      sequence_number=event.sequence_number,
      event_type=event.event_type,
      actor_user_id=event.actor_user_id,
      occurred_at=event.occurred_at,
      payload=event.payload,
      citizen_visible=event.citizen_visible,
      public_status=event.public_status,
      public_message=event.public_message,
    )

  @staticmethod
  def to_work_item(work_item: TicketWorkItem) -> TicketWorkItemResponse:
    """Converts a projected parallel task into its API representation."""

    return TicketWorkItemResponse(
      id=work_item.id,
      ticket_id=work_item.ticket_id,
      group_id=work_item.group_id,
      kind=work_item.kind,
      status=work_item.status,
      outcome=work_item.outcome,
      assignee_user_id=work_item.assignee_user_id,
      requested_by_user_id=work_item.requested_by_user_id,
      return_to_user_id=work_item.return_to_user_id,
      is_blocking=work_item.is_blocking,
      comment=work_item.comment,
      created_at=work_item.created_at,
      completed_at=work_item.completed_at,
    )
