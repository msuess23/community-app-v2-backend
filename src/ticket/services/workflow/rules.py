"""Shared validation helpers for ticket workflow commands."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import WorkflowValidationException
from src.ticket.events import TicketWorkflowState
from src.ticket.models import Ticket
from src.user.models import Role, User
from src.user.repository import UserRepository


STAFF_ROLES = {Role.OFFICER, Role.MANAGER}


def require_current_coordinator(ticket: Ticket, current_user: User) -> None:
  """Ensure the caller currently owns the main workflow responsibility."""

  if (
    current_user.role not in STAFF_ROLES
    or ticket.current_responsible_user_id != current_user.id
  ):
    raise WorkflowValidationException(
      "Only the currently responsible employee may perform this action."
    )


def require_active_processing(ticket: Ticket, message: str) -> None:
  """Reject commands outside the normal active processing state."""

  if ticket.workflow_state != TicketWorkflowState.IN_PROGRESS:
    raise WorkflowValidationException(message)


async def require_active_staff(
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
