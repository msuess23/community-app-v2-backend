from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import ConflictException
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.services.lifecycle_guard import TicketLifecycleGuard


@pytest.mark.asyncio
async def test_user_guard_rejects_active_ticket_dependency(monkeypatch) -> None:
  monkeypatch.setattr(
    TicketProjectionRepository,
    "has_active_user_dependency",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as error:
    await TicketLifecycleGuard.ensure_user_is_not_required(
      AsyncMock(),
      uuid4(),
      operation="deactivated",
    )

  assert error.value.error_code == "USER_HAS_ACTIVE_TICKETS"


@pytest.mark.asyncio
async def test_office_guard_rejects_active_ticket(monkeypatch) -> None:
  monkeypatch.setattr(
    TicketProjectionRepository,
    "has_active_tickets_for_office",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as error:
    await TicketLifecycleGuard.ensure_office_has_no_active_tickets(
      AsyncMock(),
      uuid4(),
    )

  assert error.value.error_code == "OFFICE_HAS_ACTIVE_TICKETS"
