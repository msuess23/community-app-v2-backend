"""Centralized ticket authorization rules shared by all use cases."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.ticket.events import TicketVisibility
from src.ticket.models import Ticket
from src.user.models import Role, User


STAFF_ROLES = {Role.OFFICER, Role.MANAGER}


class TicketAccessPolicy:
  """Evaluate public, citizen and authority-side ticket permissions."""

  @staticmethod
  async def can_view(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User | None,
  ) -> bool:
    """Check whether a caller may see the public ticket representation."""

    del db
    if ticket.visibility == TicketVisibility.PUBLIC:
      return True
    if current_user is None:
      return False
    if current_user.id == ticket.creator_user_id:
      return True
    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role in STAFF_ROLES:
      return (
        current_user.id
        in {
          ticket.primary_officer_id,
          ticket.current_responsible_user_id,
          ticket.pending_return_to_user_id,
        }
        or (
          current_user.office_id is not None
          and current_user.office_id == ticket.office_id
        )
      )
    return False

  @staticmethod
  async def can_view_internal(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> bool:
    """Check access to internal workflow data without granting admin access."""

    del db
    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role not in STAFF_ROLES:
      return False
    return (
      current_user.id
      in {
        ticket.primary_officer_id,
        ticket.current_responsible_user_id,
        ticket.pending_return_to_user_id,
      }
      or (
        current_user.office_id is not None
        and current_user.office_id == ticket.office_id
      )
    )
