"""Centralized ticket authorization rules shared by all use cases."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.ticket.domain import TicketVisibility, TicketWorkflowState
from src.ticket.models import Ticket
from src.user.models import Role, User


CASE_WORKER_ROLES = frozenset({Role.OFFICER, Role.MANAGER})
ROUTING_STATES = frozenset(
  {
    TicketWorkflowState.NEW,
    TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
  }
)


class TicketAccessPolicy:
  """Evaluate public, citizen and authority-side ticket permissions."""

  @staticmethod
  def is_case_worker_participant(ticket: Ticket, current_user: User) -> bool:
    """Return whether a case worker belongs to the ticket or its office."""

    if current_user.role not in CASE_WORKER_ROLES:
      return False
    return (
      current_user.id
      in {
        ticket.primary_officer_id,
        ticket.current_assignee_id,
        ticket.return_to_user_id,
      }
      or (
        current_user.office_id is not None
        and current_user.office_id == ticket.office_id
      )
    )

  @staticmethod
  def is_dispatcher_routing_ticket(ticket: Ticket, current_user: User) -> bool:
    """Return whether a dispatcher may inspect the current routing stage."""

    return (
      current_user.role == Role.DISPATCHER
      and ticket.workflow_state in ROUTING_STATES
    )

  @staticmethod
  async def can_view(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User | None,
  ) -> bool:
    """Check whether a caller may see the citizen-facing representation."""

    del db
    if ticket.visibility == TicketVisibility.PUBLIC:
      return True
    if current_user is None:
      return False
    if current_user.id == ticket.creator_user_id:
      return True
    return (
      TicketAccessPolicy.is_dispatcher_routing_ticket(ticket, current_user)
      or TicketAccessPolicy.is_case_worker_participant(ticket, current_user)
    )

  @staticmethod
  async def can_view_internal(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> bool:
    """Check access to internal workflow data without granting admin access."""

    del db
    return (
      TicketAccessPolicy.is_dispatcher_routing_ticket(ticket, current_user)
      or TicketAccessPolicy.is_case_worker_participant(ticket, current_user)
    )

  @staticmethod
  def can_manage_images(ticket: Ticket, current_user: User) -> bool:
    """Return whether authority staff may change the current image projection."""

    return (
      ticket.workflow_state != TicketWorkflowState.COMPLETED
      and TicketAccessPolicy.is_case_worker_participant(ticket, current_user)
    )
