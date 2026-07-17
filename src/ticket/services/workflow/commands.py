"""Main-path commands for the ticket ad-hoc workflow.

This module contains commands that transfer overall responsibility, wait for an
external decision, or complete the aggregate. Parallel task commands stay in
``workflow_service.py`` because they update the separate work-item projection.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
  ForbiddenException,
  WorkflowValidationException,
)
from src.ticket.events import (
  CitizenRespondedPayload,
  CitizenResponseRequestedPayload,
  EscalationDecisionPayload,
  TicketCompletedPayload,
  TicketEscalatedPayload,
  TicketEventType,
  TicketForwardedPayload,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.repository import TicketRepository
from src.ticket.schemas import (
  ApproveEscalationAction,
  EscalateTicketAction,
  ForwardTicketAction,
  RejectEscalationAction,
  RejectTicketAction,
  RequestCitizenResponseAction,
  ResolveTicketAction,
  TicketCitizenResponseRequest,
)
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.ticket.services.workflow.rules import (
  require_active_processing,
  require_active_staff,
  require_current_coordinator,
  require_no_blocking_tasks,
)
from src.user.models import Role, User


class TicketWorkflowCommandService:
  """Applies validated commands that change the ticket's main workflow path."""

  @staticmethod
  async def forward_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: ForwardTicketAction,
    current_user: User,
  ) -> Ticket:
    """Transfers current coordination while retaining the primary officer."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Only actively processed tickets may be forwarded.")
    await require_no_blocking_tasks(db, ticket)

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
  async def escalate_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: EscalateTicketAction,
    current_user: User,
  ) -> Ticket:
    """Temporarily transfers coordination to a manager for a decision."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)
    require_active_processing(ticket, "Only actively processed tickets may be escalated.")
    await require_no_blocking_tasks(db, ticket)

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
  async def approve_escalation(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: ApproveEscalationAction,
    current_user: User,
  ) -> Ticket:
    """Approves a pending escalation and returns it to the requesting employee."""

    return await TicketWorkflowCommandService._decide_escalation(
      db,
      ticket_id,
      current_user=current_user,
      event_type=TicketEventType.ESCALATION_APPROVED,
      comment=request.comment,
    )

  @staticmethod
  async def reject_escalation(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: RejectEscalationAction,
    current_user: User,
  ) -> Ticket:
    """Rejects an escalation without rejecting the underlying citizen ticket."""

    return await TicketWorkflowCommandService._decide_escalation(
      db,
      ticket_id,
      current_user=current_user,
      event_type=TicketEventType.ESCALATION_REJECTED,
      comment=request.comment,
    )

  @staticmethod
  async def _decide_escalation(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    *,
    current_user: User,
    event_type: TicketEventType,
    comment: str | None,
  ) -> Ticket:
    """Applies one decision to the currently pending manager escalation."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may decide escalations")
    if (
      ticket.workflow_state != TicketWorkflowState.WAITING_FOR_APPROVAL
      or ticket.current_responsible_user_id != current_user.id
      or ticket.pending_return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket has no escalation for this manager.")

    return_to = await require_active_staff(
      db,
      ticket.pending_return_to_user_id,
      error_message="The employee awaiting the decision is no longer active.",
    )
    await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=event_type,
      payload=EscalationDecisionPayload(
        return_to_user_id=return_to.id,
        comment=comment,
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
    """Pauses authority processing until the citizen supplies missing details."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)
    require_active_processing(
      ticket,
      "Citizen information can only be requested during active processing.",
    )
    await require_no_blocking_tasks(db, ticket)

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
    """Appends the creator's response and returns the case to the requester."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if current_user.role != Role.CITIZEN or ticket.creator_user_id != current_user.id:
      raise ForbiddenException("Only the ticket creator may answer this request")
    if (
      ticket.workflow_state != TicketWorkflowState.WAITING_FOR_CITIZEN
      or ticket.current_responsible_user_id != current_user.id
      or ticket.pending_return_to_user_id is None
    ):
      raise WorkflowValidationException("This ticket is not waiting for a citizen response.")

    return_to = await require_active_staff(
      db,
      ticket.pending_return_to_user_id,
      error_message="The requesting employee is no longer active.",
    )
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
  async def resolve_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: ResolveTicketAction,
    current_user: User,
  ) -> Ticket:
    """Completes an actively processed ticket successfully."""

    return await TicketWorkflowCommandService._complete_ticket(
      db,
      ticket_id,
      current_user=current_user,
      event_type=TicketEventType.TICKET_RESOLVED,
      message=request.message,
      manager_only=False,
    )

  @staticmethod
  async def reject_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: RejectTicketAction,
    current_user: User,
  ) -> Ticket:
    """Ends an actively processed ticket as rejected."""

    return await TicketWorkflowCommandService._complete_ticket(
      db,
      ticket_id,
      current_user=current_user,
      event_type=TicketEventType.TICKET_REJECTED,
      message=request.message,
      manager_only=True,
    )

  @staticmethod
  async def _complete_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    *,
    current_user: User,
    event_type: TicketEventType,
    message: str,
    manager_only: bool,
  ) -> Ticket:
    """Applies one terminal event after all active work items are finished."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)
    if manager_only and current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may reject a ticket")
    require_active_processing(ticket, "Only actively processed tickets may be completed.")
    if await TicketRepository.has_open_work_items(db, ticket.id):
      raise WorkflowValidationException(
        "Complete or cancel all work items before completing the ticket."
      )

    await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=event_type,
      payload=TicketCompletedPayload(message=message),
    )
    return ticket
