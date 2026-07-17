"""Shared authorization and precondition helpers for ticket workflow commands."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, WorkflowValidationException
from src.ticket.events import TicketWorkflowState
from src.ticket.models import Ticket
from src.ticket.repository import TicketRepository
from src.user.models import Role, User
from src.user.repository import UserRepository


STAFF_ROLES = {Role.OFFICER, Role.MANAGER}


async def require_active_staff(
  db: AsyncSession,
  user_id: uuid.UUID,
  *,
  roles: set[Role] = STAFF_ROLES,
  error_message: str = "The selected user is not an active staff member.",
) -> User:
  """Loads one active employee whose role is valid for a workflow command."""

  user = await UserRepository.get_by_id(db, user_id)
  if user is None or not user.is_active or user.role not in roles:
    raise WorkflowValidationException(error_message)
  return user


def require_current_coordinator(ticket: Ticket, current_user: User) -> None:
  """Ensures that only the current coordinator changes the main workflow path."""

  if current_user.role not in STAFF_ROLES:
    raise ForbiddenException("Only authority staff may execute this action")
  if ticket.current_responsible_user_id != current_user.id:
    raise ForbiddenException("Only the current responsible user may execute this action")


async def require_no_blocking_tasks(db: AsyncSession, ticket: Ticket) -> None:
  """Prevents the main workflow from bypassing unfinished blocking reviews."""

  if await TicketRepository.has_open_blocking_work_items(db, ticket.id):
    raise WorkflowValidationException(
      "Complete or cancel all blocking work items before continuing the main workflow."
    )


def require_active_processing(ticket: Ticket, message: str) -> None:
  """Requires the regular staff-processing phase for a workflow transition."""

  if ticket.workflow_state != TicketWorkflowState.IN_PROGRESS:
    raise WorkflowValidationException(message)
