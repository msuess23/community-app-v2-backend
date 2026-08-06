"""Repository-level ordering guarantees for appointment event pages."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.appointment.repository import AppointmentEventRepository
from src.core.filters import SortOrder


@pytest.mark.asyncio
async def test_event_page_orders_newest_events_first(monkeypatch) -> None:
  execute_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(
    "src.appointment.repository.execute_page",
    execute_page,
  )

  await AppointmentEventRepository.get_event_page(
    AsyncMock(),
    uuid4(),
    page=1,
    size=20,
  )

  assert execute_page.await_args.kwargs["order"] == SortOrder.DESC
