"""Shared ticket workflow permissions, selectable targets and outcomes."""

from __future__ import annotations

from src.office.models import Office
from src.ticket.domain import (
  TicketCompletionOutcome,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.ticket.services.errors import (
  TicketActionNotAllowedException,
  TicketSelfTargetException,
  TicketTargetNotEligibleException,
  TicketTargetUnavailableException,
)
from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


class TicketWorkflowPolicy:
  """Provide one source of truth for action and target eligibility."""

  ROUTING_STATES = frozenset(
    {
      TicketWorkflowState.NEW,
      TicketWorkflowState.RETURNED_TO_DISPATCH,
      TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    }
  )

  @staticmethod
  def allowed_actions(ticket: Ticket, actor: User) -> list[TicketWorkflowAction]:
    """Return actions currently executable by one authority user."""

    actions: list[TicketWorkflowAction] = []
    if (
      actor.role == Role.DISPATCHER
      and ticket.primary_officer_id is None
      and ticket.workflow_state in TicketWorkflowPolicy.ROUTING_STATES
    ):
      actions.append(TicketWorkflowAction.DISPATCH)

    if (
      actor.role == Role.MANAGER
      and actor.office_id == ticket.office_id
      and ticket.workflow_state != TicketWorkflowState.COMPLETED
    ):
      if (
        ticket.primary_officer_id is None
        and ticket.workflow_state == TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
      ):
        actions.append(TicketWorkflowAction.ASSIGN_PRIMARY_OFFICER)
      elif ticket.primary_officer_id is not None:
        actions.append(TicketWorkflowAction.REASSIGN_PRIMARY_OFFICER)

    is_assignee = (
      actor.role in CASE_WORKER_ROLES and ticket.current_assignee_id == actor.id
    )
    if is_assignee and ticket.workflow_state == TicketWorkflowState.IN_PROGRESS:
      actions.extend(
        [
          TicketWorkflowAction.FORWARD,
          TicketWorkflowAction.REQUEST_COSIGNATURE,
          TicketWorkflowAction.ESCALATE,
          TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
          TicketWorkflowAction.RETURN_TO_DISPATCH,
          TicketWorkflowAction.COMPLETE,
        ]
      )

    if (
      is_assignee
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_COSIGNATURE
      and ticket.return_to_user_id is not None
    ):
      actions.append(TicketWorkflowAction.COSIGN)

    if (
      actor.role == Role.MANAGER
      and ticket.current_assignee_id == actor.id
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_DECISION
      and ticket.return_to_user_id is not None
    ):
      actions.append(TicketWorkflowAction.DECIDE_ESCALATION)

    return actions

  @staticmethod
  def require_action(ticket: Ticket, actor: User, action: TicketWorkflowAction) -> None:
    """Raise a stable conflict when an action is absent from the policy result."""

    if action not in TicketWorkflowPolicy.allowed_actions(ticket, actor):
      raise TicketActionNotAllowedException()

  @staticmethod
  def office_is_eligible(office: Office | None) -> bool:
    """Return whether an office may receive a dispatch command."""

    return office is not None and bool(office.is_active)

  @staticmethod
  def primary_officer_is_eligible(ticket: Ticket, user: User | None) -> bool:
    """Return whether a user may become permanent owner of this ticket."""

    return bool(
      user is not None
      and user.is_active
      and user.role == Role.OFFICER
      and user.office_id == ticket.office_id
    )

  @staticmethod
  def processing_target_is_eligible(user: User | None) -> bool:
    """Return whether a user may receive forwarding or cosignature work."""

    return bool(user is not None and user.is_active and user.role in CASE_WORKER_ROLES)

  @staticmethod
  def escalation_target_is_eligible(user: User | None) -> bool:
    """Return whether a user may decide a ticket escalation."""

    return bool(user is not None and user.is_active and user.role == Role.MANAGER)

  @staticmethod
  def require_target(
    *,
    target: User | None,
    actor: User,
    eligible: bool,
    role_message: str,
  ) -> User:
    """Apply availability, role and self-target checks in a stable order."""

    if target is None or not target.is_active:
      raise TicketTargetUnavailableException()
    if target.id == actor.id:
      raise TicketSelfTargetException()
    if not eligible:
      raise TicketTargetNotEligibleException(role_message)
    return target

  @staticmethod
  def completion_outcomes(actor: User) -> list[TicketCompletionOutcome]:
    """Return terminal outcomes available to the current case worker."""

    outcomes = [TicketCompletionOutcome.RESOLVED]
    if actor.role == Role.MANAGER:
      outcomes.append(TicketCompletionOutcome.REJECTED)
    return outcomes
