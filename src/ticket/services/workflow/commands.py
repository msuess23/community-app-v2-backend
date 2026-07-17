"""Commands for the simplified sequential ticket ad-hoc workflow."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, WorkflowValidationException
from src.ticket.events import (
  CitizenRespondedPayload,
  CitizenResponseRequestedPayload,
  CosignatureRequestedPayload,
  EscalationDecisionPayload,
  TicketCompletedPayload,
  TicketCosignedPayload,
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
  RequestCitizenResponseAction,
  RequestCosignatureAction,
  TicketCitizenResponseRequest,
)
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.ticket.services.workflow.rules import (
  require_active_processing,
  require_active_staff,
  require_current_coordinator,
)
from src.user.models import Role, User


class TicketWorkflowCommandService:
  """Apply commands that move the ticket through its sequential workflow."""

  @staticmethod
  async def forward_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: ForwardTicketAction,
    current_user: User,
  ) -> Ticket:
    """Transfer coordination while retaining the permanent primary officer."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Only active tickets may be forwarded.")
    target = await require_active_staff(db, request.target_user_id)
    if target.id == current_user.id:
      raise WorkflowValidationException("A ticket cannot be forwarded to the same user.")

    await TicketEventStore._append_event(
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
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Cosignatures require active processing.")
    target = await require_active_staff(db, request.target_user_id)
    if target.id == current_user.id:
      raise WorkflowValidationException("A user cannot request their own cosignature.")

    await TicketEventStore._append_event(
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
      or ticket.current_responsible_user_id != current_user.id
      or ticket.pending_return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket is not awaiting your cosignature.")
    return_to = await require_active_staff(db, ticket.pending_return_to_user_id)
    await TicketEventStore._append_event(
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
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Only active tickets may be escalated.")
    manager = await require_active_staff(
      db,
      request.manager_user_id,
      roles={Role.MANAGER},
      error_message="The escalation target must be an active manager.",
    )
    if manager.id == current_user.id:
      raise WorkflowValidationException("A user cannot escalate a ticket to themselves.")

    await TicketEventStore._append_event(
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
      or ticket.current_responsible_user_id != current_user.id
      or ticket.pending_return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket has no escalation for this manager.")
    return_to = await require_active_staff(db, ticket.pending_return_to_user_id)

    await TicketEventStore._append_event(
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
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Citizen input requires active processing.")
    await TicketEventStore._append_event(
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
      or ticket.current_responsible_user_id != current_user.id
      or ticket.pending_return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket is not waiting for a citizen response.")
    return_to = await require_active_staff(db, ticket.pending_return_to_user_id)
    event = await TicketEventStore._append_event(
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
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Only active tickets may be completed.")
    if request.outcome.value == "REJECTED" and current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may reject a ticket")

    await TicketEventStore._append_event(
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
