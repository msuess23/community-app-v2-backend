"""Centralized ticket authorization and capability calculation."""

from __future__ import annotations

from dataclasses import dataclass

from src.ticket.domain import TicketVisibility, TicketWorkflowState
from src.ticket.models import Ticket
from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


ROUTING_STATES = frozenset(
  {
    TicketWorkflowState.NEW,
    TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
  }
)


@dataclass(frozen=True)
class TicketCapabilities:
  """Actions exposed by a ticket response and enforced by command services."""

  can_edit: bool = False
  can_manage_images: bool = False
  can_comment: bool = False
  can_view_internal: bool = False


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
  def can_view(ticket: Ticket, current_user: User | None) -> bool:
    """Check whether a caller may see the citizen-facing representation."""

    if ticket.visibility == TicketVisibility.PUBLIC:
      return True
    if current_user is None:
      return False
    if current_user.id == ticket.creator_user_id:
      return True
    return TicketAccessPolicy.can_view_internal(ticket, current_user)

  @staticmethod
  def can_view_internal(ticket: Ticket, current_user: User) -> bool:
    """Check access to internal workflow data without granting admin access."""

    return (
      TicketAccessPolicy.is_dispatcher_routing_ticket(ticket, current_user)
      or TicketAccessPolicy.is_case_worker_participant(ticket, current_user)
    )

  @staticmethod
  def capabilities(ticket: Ticket, current_user: User | None) -> TicketCapabilities:
    """Calculate response flags from the same rules used by commands."""

    if current_user is None:
      return TicketCapabilities()

    is_creator = current_user.id == ticket.creator_user_id
    can_edit = is_creator and ticket.workflow_state == TicketWorkflowState.NEW
    can_view_internal = TicketAccessPolicy.can_view_internal(ticket, current_user)
    can_manage_images = can_edit or (
      current_user.role in CASE_WORKER_ROLES
      and can_view_internal
      and ticket.workflow_state != TicketWorkflowState.COMPLETED
    )
    can_comment = (
      is_creator and ticket.workflow_state != TicketWorkflowState.COMPLETED
    ) or can_view_internal
    return TicketCapabilities(
      can_edit=can_edit,
      can_manage_images=can_manage_images,
      can_comment=can_comment,
      can_view_internal=can_view_internal,
    )

  @staticmethod
  def can_manage_images(ticket: Ticket, current_user: User) -> bool:
    """Return whether the caller may change the current image projection."""

    return TicketAccessPolicy.capabilities(ticket, current_user).can_manage_images
