"""Cross-domain guards that protect active ticket workflows."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException
from src.ticket.repositories.ticket import TicketProjectionRepository


class TicketLifecycleGuard:
  """Prevents user and office lifecycle changes from orphaning active tickets."""

  @staticmethod
  async def ensure_user_is_not_required(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    operation: str,
  ) -> None:
    """Reject a lifecycle change while a user is referenced by an active ticket."""

    if await TicketProjectionRepository.has_active_user_dependency(db, user_id):
      raise ConflictException(
        f"User cannot be {operation} while referenced by an active ticket.",
        error_code="USER_HAS_ACTIVE_TICKETS",
      )

  @staticmethod
  async def ensure_office_has_no_active_tickets(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> None:
    """Reject office deactivation while unfinished tickets remain assigned."""

    if await TicketProjectionRepository.has_active_tickets_for_office(db, office_id):
      raise ConflictException(
        "Office cannot be deactivated while active tickets are assigned to it.",
        error_code="OFFICE_HAS_ACTIVE_TICKETS",
      )
