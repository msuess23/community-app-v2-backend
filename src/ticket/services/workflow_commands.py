"""Commands for office assignment and the sequential ticket workflow."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException
from src.office.repository import OfficeRepository
from src.ticket.domain import (
  CitizenRespondedPayload,
  CitizenResponseRequestedPayload,
  CosignatureRequestedPayload,
  EscalationDecisionPayload,
  PrimaryOfficerAssignedPayload,
  PrimaryOfficerReassignedPayload,
  TicketCompletedPayload,
  TicketCosignedPayload,
  TicketDispatchedPayload,
  TicketEscalatedPayload,
  TicketEventType,
  TicketForwardedPayload,
  TicketReturnedToDispatchPayload,
  TicketWorkflowAction,
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
  ReturnToDispatchAction,
  TicketCitizenResponseRequest,
  TicketDispatchRequest,
  TicketWorkflowRequest,
)
from src.ticket.services.errors import (
  TicketActionNotAllowedException,
  TicketCompletionOutcomeNotAllowedException,
  TicketSelfTargetException,
  TicketTargetAlreadySelectedException,
  TicketTargetNotEligibleException,
  TicketTargetUnavailableException,
)
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.ticket.services.workflow_policy import TicketWorkflowPolicy
from src.user.models import Role, User
from src.user.repository import UserRepository


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
  """Load a workflow target without applying role-specific policy twice."""

  return await UserRepository.get_by_id(db, user_id)


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
    TicketWorkflowPolicy.require_action(
      ticket,
      current_user,
      TicketWorkflowAction.DISPATCH,
    )
    office = await OfficeRepository.get_by_id(db, request.office_id)
    if not TicketWorkflowPolicy.office_is_eligible(office):
      raise TicketTargetUnavailableException("The selected office is no longer available.")
    assert office is not None

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_DISPATCHED,
      payload=TicketDispatchedPayload(office_id=office.id, comment=request.comment),
    )
    return ticket

  @staticmethod
  async def assign_primary_officer(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: PrimaryOfficerAssignmentRequest,
    current_user: User,
  ) -> Ticket:
    """Assign or replace the permanent case owner for the responsible office."""

    if current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may assign a primary officer")
    ticket = await require_ticket(db, ticket_id, for_update=True)
    action = (
      TicketWorkflowAction.ASSIGN_PRIMARY_OFFICER
      if ticket.primary_officer_id is None
      else TicketWorkflowAction.REASSIGN_PRIMARY_OFFICER
    )
    TicketWorkflowPolicy.require_action(ticket, current_user, action)
    officer = await _load_user(db, request.primary_officer_id)
    if officer is None or not officer.is_active:
      raise TicketTargetUnavailableException()
    if officer.id == ticket.primary_officer_id:
      raise TicketTargetAlreadySelectedException(
        "The selected officer is already the primary officer."
      )
    if not TicketWorkflowPolicy.primary_officer_is_eligible(ticket, officer):
      raise TicketTargetNotEligibleException(
        "The primary officer must be an active officer of the assigned office."
      )

    if ticket.primary_officer_id is None:
      event_type = TicketEventType.PRIMARY_OFFICER_ASSIGNED
      payload = PrimaryOfficerAssignedPayload(
        primary_officer_id=officer.id,
        comment=request.comment,
      )
    else:
      event_type = TicketEventType.PRIMARY_OFFICER_REASSIGNED
      payload = PrimaryOfficerReassignedPayload(
        previous_primary_officer_id=ticket.primary_officer_id,
        new_primary_officer_id=officer.id,
        comment=request.comment,
      )

    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=event_type,
      payload=payload,
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
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    target = await _load_user(db, request.target_user_id)
    target = TicketWorkflowPolicy.require_target(
      target=target,
      actor=current_user,
      eligible=TicketWorkflowPolicy.processing_target_is_eligible(target),
      role_message="Tickets may only be forwarded to active officers or managers.",
    )
    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_FORWARDED,
      payload=TicketForwardedPayload(target_user_id=target.id, comment=request.comment),
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
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    target = await _load_user(db, request.target_user_id)
    target = TicketWorkflowPolicy.require_target(
      target=target,
      actor=current_user,
      eligible=TicketWorkflowPolicy.processing_target_is_eligible(target),
      role_message="Cosignatures may only be requested from active officers or managers.",
    )
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
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    assert ticket.return_to_user_id is not None
    return_to = await _load_user(db, ticket.return_to_user_id)
    if return_to is None or not TicketWorkflowPolicy.processing_target_is_eligible(return_to):
      raise TicketTargetUnavailableException("The return target is no longer available.")
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
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    manager = await _load_user(db, request.manager_user_id)
    manager = TicketWorkflowPolicy.require_target(
      target=manager,
      actor=current_user,
      eligible=TicketWorkflowPolicy.escalation_target_is_eligible(manager),
      role_message="The escalation target must be an active manager.",
    )
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
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    assert ticket.return_to_user_id is not None
    return_to = await _load_user(db, ticket.return_to_user_id)
    if return_to is None or not TicketWorkflowPolicy.processing_target_is_eligible(return_to):
      raise TicketTargetUnavailableException("The return target is no longer available.")
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
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
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
      raise TicketActionNotAllowedException(
        "This ticket is not waiting for a citizen response."
      )
    return_to = await _load_user(db, ticket.return_to_user_id)
    if return_to is None or not TicketWorkflowPolicy.processing_target_is_eligible(return_to):
      raise TicketTargetUnavailableException("The return target is no longer available.")
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
  async def return_to_dispatch(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: ReturnToDispatchAction,
    current_user: User,
  ) -> Ticket:
    """Return an incorrectly assigned active ticket to the central inbox."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    assert ticket.office_id is not None
    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_RETURNED_TO_DISPATCH,
      payload=TicketReturnedToDispatchPayload(
        previous_office_id=ticket.office_id,
        previous_primary_officer_id=ticket.primary_officer_id,
        reason=request.reason,
      ),
    )
    return ticket

  @staticmethod
  async def complete_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CompleteTicketAction,
    current_user: User,
  ) -> Ticket:
    """Complete a ticket with the requested public outcome."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    TicketWorkflowPolicy.require_action(ticket, current_user, request.action)
    if request.outcome not in TicketWorkflowPolicy.completion_outcomes(current_user):
      raise TicketCompletionOutcomeNotAllowedException()
    await TicketEventStore.append(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_COMPLETED,
      payload=TicketCompletedPayload(outcome=request.outcome, message=request.message),
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
      ReturnToDispatchAction: TicketWorkflowCommandService.return_to_dispatch,
      CompleteTicketAction: TicketWorkflowCommandService.complete_ticket,
    }
    for request_type, handler in handlers.items():
      if isinstance(request, request_type):
        return await handler(db, ticket_id, request, current_user)
    raise TicketActionNotAllowedException("Unsupported workflow action.")
