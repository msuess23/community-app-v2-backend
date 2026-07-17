"""Centralized ticket authorization rules shared by all use cases."""

from __future__ import annotations


from sqlalchemy.ext.asyncio import AsyncSession

from src.ticket.events import (
  TicketVisibility,
)
from src.ticket.models import Ticket
from src.ticket.repository import TicketRepository
from src.user.models import Role, User

STAFF_ROLES = {Role.OFFICER, Role.MANAGER}


class TicketAccessPolicy:
  """Evaluates citizen, public and authority-side ticket permissions."""

  @staticmethod
  async def can_view(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User | None,
  ) -> bool:
    """Checks public, creator and authority-side access to one ticket."""

    if ticket.visibility == TicketVisibility.PUBLIC:
      return True
    if current_user is None:
      return False
    if current_user.id == ticket.creator_user_id:
      return True
    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role in {Role.OFFICER, Role.MANAGER}:
      if current_user.id in {
        ticket.primary_officer_id,
        ticket.current_responsible_user_id,
      }:
        return True
      if current_user.office_id is not None and current_user.office_id == ticket.office_id:
        return True
      return await TicketRepository.has_open_work_item_for_user(
        db,
        ticket.id,
        current_user.id,
      )
    return False

  @staticmethod
  async def can_view_internal(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> bool:
    """Checks access to internal workflow data without granting admin access."""

    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role not in STAFF_ROLES:
      return False
    if current_user.id in {
      ticket.primary_officer_id,
      ticket.current_responsible_user_id,
      ticket.pending_return_to_user_id,
    }:
      return True
    if current_user.office_id is not None and current_user.office_id == ticket.office_id:
      return True
    return await TicketRepository.has_open_work_item_for_user(
      db,
      ticket.id,
      current_user.id,
    )
