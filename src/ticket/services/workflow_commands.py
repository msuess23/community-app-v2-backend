"""Commands for office assignment and the sequential ticket workflow."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, WorkflowValidationException
from src.office.repository import OfficeRepository
from src.ticket.domain import (
  CitizenRespondedPayload,
  CitizenResponseRequestedPayload,
  CosignatureRequestedPayload,
  EscalationDecisionPayload,
  PrimaryOfficerAssignedPayload,
  TicketCompletedPayload,
  TicketCosignedPayload,
  TicketDispatchedPayload,
  TicketEscalatedPayload,
  TicketEventType,
  TicketForwardedPayload,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import (
  CompleteTicketAction,
  CosignTicketAction,
  DecideEscalationAction,
  EscalateTicketAction,
  ForwardTicketAction,
  PrimaryOfficerAssignmentRequest,
  RequestCitizenResponseAction,
  RequestCosignatureAction,
  TicketCitizenResponseRequest,
  TicketDispatchRequest,
  TicketWorkflowRequest,
)
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.user.models import Role, User
from src.user.repository import UserRepository


STAFF_ROLES = {Role.OFFICER, Role.MANAGER}


def _require_current_assignee(ticket: Ticket, current_user: User) -> None:
  """Ensure the caller currently owns the main workflow responsibility."""

  if current_user.role not in STAFF_ROLES or ticket.current_assignee_id != current_user.id:
    raise WorkflowValidationException(
      "Only the currently assigned employee may perform this action."
    )


def _require_active_processing(ticket: Ticket, message: str) -> None:
  """Reject commands outside the normal active processing state."""

  if ticket.workflow_state != TicketWorkflowState.IN_PROGRESS:
    raise WorkflowValidationException(message)


async def _require_active_staff(
  db: AsyncSession,
  user_id: uuid.UUID,
  *,
  roles: set[Role] | None = None,
  error_message: str = "The selected employee is not active.",
) -> User:
  """Load an active authority employee matching optional role constraints."""

  user = await UserRepository.get_by_id(db, user_id)
  allowed_roles = roles or STAFF_ROLES
  if user is None or not user.is_active or user.role not in allowed_roles:
    raise WorkflowValidationException(error_message)
  return user


class TicketWorkflowCommandService:
  """Apply assignment and sequential ad-hoc workflow commands."""

  @staticmethod
  async def dispatch_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketDispatchRequest,
    current_user: User,
  ) -> Ticket:
    """Assign a central-inbox ticket to an active office."""

    if current_user.role != Role.DISPATCHER:
      raise ForbiddenException("Only dispatchers may route tickets")

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if ticket.primary_officer_id is not None or ticket.workflow_state not in {
      TicketWorkflowState.NEW,
      TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    }:
      raise WorkflowValidationException(
        "Only tickets without a primary officer may be dispatched."
      )

    office = await OfficeRepository.get_by_id(db, request.office_id)
    if office is None or not office.is_active:
      raise WorkflowValidationException("The selected office is not active.")

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_DISPATCHED,
      payload=TicketDispatchedPayload(
        office_id=office.id,
        comment=request.comment,
      ),
    )
    return ticket

  @staticmethod
  async def assign_primary_officer(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: PrimaryOfficerAssignmentRequest,
    current_user: User,
  ) -> Ticket:
    """Let the responsible office manager select the permanent case owner."""

    if current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may assign a primary officer")

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if (
      ticket.workflow_state != TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
      or ticket.office_id is None
      or ticket.primary_officer_id is not None
    ):
      raise WorkflowValidationException(
        "The ticket is not waiting for its initial primary officer."
      )
    if current_user.office_id != ticket.office_id:
      raise ForbiddenException("Only a manager of the assigned office may act")

    officer = await _require_active_staff(
      db,
      request.primary_officer_id,
      roles={Role.OFFICER},
      error_message=(
        "The primary officer must be an active officer of the assigned office."
      ),
    )
    if officer.office_id != ticket.office_id:
      raise WorkflowValidationException(
        "The primary officer must be an active officer of the assigned office."
      )

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.PRIMARY_OFFICER_ASSIGNED,
      payload=PrimaryOfficerAssignedPayload(
        primary_officer_id=officer.id,
        comment=request.comment,
      ),
    )
    return ticket

  @staticmethod
  async def forward_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: ForwardTicketAction,
    current_user: User,
  ) -> Ticket:
    """Transfer coordination while retaining the permanent primary officer."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    _require_current_assignee(ticket, current_user)
    _require_active_processing(ticket, "Only active tickets may be forwarded.")
    target = await _require_active_staff(db, request.target_user_id)
    if target.id == current_user.id:
      raise WorkflowValidationException("A ticket cannot be forwarded to the same user.")

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_FORWARDED,
      payload=TicketForwardedPayload(
        target_user_id=target.id,
        comment=request.comment,
      ),
    )
    return ticket

  @staticmethod
  async def request_cosignature(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: RequestCosignatureAction,
    current_user: User,
  ) -> Ticket:
    """Send the ticket to one employee for an explicit cosignature."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    _require_current_assignee(ticket, current_user)
    _require_active_processing(ticket, "Cosignatures require active processing.")
    target = await _require_active_staff(db, request.target_user_id)
    if target.id == current_user.id:
      raise WorkflowValidationException("A user cannot request their own cosignature.")

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.COSIGNATURE_REQUESTED,
      payload=CosignatureRequestedPayload(
        target_user_id=target.id,
        return_to_user_id=current_user.id,
        comment=request.comment,
      ),
    )
    return ticket

  @staticmethod
  async def cosign_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CosignTicketAction,
    current_user: User,
  ) -> Ticket:
    """Record the requested cosignature and return the case to its requester."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if (
      ticket.workflow_state != TicketWorkflowState.WAITING_FOR_COSIGNATURE
      or ticket.current_assignee_id != current_user.id
      or ticket.return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket is not awaiting your cosignature.")
    return_to = await _require_active_staff(db, ticket.return_to_user_id)
    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_COSIGNED,
      payload=TicketCosignedPayload(
        return_to_user_id=return_to.id,
        comment=request.comment,
      ),
    )
    return ticket

  @staticmethod
  async def escalate_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: EscalateTicketAction,
    current_user: User,
  ) -> Ticket:
    """Temporarily transfer coordination to a manager for one decision."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    _require_current_assignee(ticket, current_user)
    _require_active_processing(ticket, "Only active tickets may be escalated.")
    manager = await _require_active_staff(
      db,
      request.manager_user_id,
      roles={Role.MANAGER},
      error_message="The escalation target must be an active manager.",
    )
    if manager.id == current_user.id:
      raise WorkflowValidationException("A user cannot escalate a ticket to themselves.")

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_ESCALATED,
      payload=TicketEscalatedPayload(
        manager_user_id=manager.id,
        return_to_user_id=current_user.id,
        reason=request.reason,
      ),
    )
    return ticket

  @staticmethod
  async def decide_escalation(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: DecideEscalationAction,
    current_user: User,
  ) -> Ticket:
    """Apply one management decision and return the ticket to its requester."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may decide escalations")
    if (
      ticket.workflow_state != TicketWorkflowState.WAITING_FOR_DECISION
      or ticket.current_assignee_id != current_user.id
      or ticket.return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket has no escalation for this manager.")
    return_to = await _require_active_staff(db, ticket.return_to_user_id)

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.ESCALATION_DECIDED,
      payload=EscalationDecisionPayload(
        return_to_user_id=return_to.id,
        decision=request.decision,
        comment=request.comment,
      ),
    )
    return ticket

  @staticmethod
  async def request_citizen_response(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: RequestCitizenResponseAction,
    current_user: User,
  ) -> Ticket:
    """Pause authority processing until the citizen supplies missing details."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    _require_current_assignee(ticket, current_user)
    _require_active_processing(ticket, "Citizen input requires active processing.")
    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.CITIZEN_RESPONSE_REQUESTED,
      payload=CitizenResponseRequestedPayload(
        question=request.question,
        return_to_user_id=current_user.id,
      ),
    )
    return ticket

  @staticmethod
  async def respond_as_citizen(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketCitizenResponseRequest,
    current_user: User,
  ) -> tuple[Ticket, TicketEvent]:
    """Append the creator response and return the case to the requester."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if current_user.role != Role.CITIZEN or ticket.creator_user_id != current_user.id:
      raise ForbiddenException("Only the ticket creator may answer this request")
    if (
      ticket.workflow_state != TicketWorkflowState.WAITING_FOR_CITIZEN
      or ticket.current_assignee_id != current_user.id
      or ticket.return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket is not waiting for a citizen response.")
    return_to = await _require_active_staff(db, ticket.return_to_user_id)
    event = await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.CITIZEN_RESPONDED,
      payload=CitizenRespondedPayload(
        message=request.message,
        return_to_user_id=return_to.id,
      ),
    )
    return ticket, event

  @staticmethod
  async def complete_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CompleteTicketAction,
    current_user: User,
  ) -> Ticket:
    """Complete a ticket with the requested public outcome."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    _require_current_assignee(ticket, current_user)
    _require_active_processing(ticket, "Only active tickets may be completed.")
    if request.outcome.value == "REJECTED" and current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may reject a ticket")

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_COMPLETED,
      payload=TicketCompletedPayload(
        outcome=request.outcome,
        message=request.message,
      ),
    )
    return ticket

  @staticmethod
  async def execute_workflow(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketWorkflowRequest,
    current_user: User,
  ) -> Ticket:
    """Route one validated workflow request to its command handler."""

    handlers = {
      ForwardTicketAction: TicketWorkflowCommandService.forward_ticket,
      RequestCosignatureAction: TicketWorkflowCommandService.request_cosignature,
      CosignTicketAction: TicketWorkflowCommandService.cosign_ticket,
      EscalateTicketAction: TicketWorkflowCommandService.escalate_ticket,
      DecideEscalationAction: TicketWorkflowCommandService.decide_escalation,
      RequestCitizenResponseAction: TicketWorkflowCommandService.request_citizen_response,
      CompleteTicketAction: TicketWorkflowCommandService.complete_ticket,
    }
    for request_type, handler in handlers.items():
      if isinstance(request, request_type):
        return await handler(db, ticket_id, request, current_user)
    raise WorkflowValidationException("Unsupported workflow action.")
