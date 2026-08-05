from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.filters import SortOrder
from src.ticket.repositories.event import TicketEventRepository


@pytest.mark.asyncio
async def test_internal_event_page_orders_newest_events_first(monkeypatch) -> None:
  execute_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(
    "src.ticket.repositories.event.execute_page",
    execute_page,
  )

  await TicketEventRepository.get_event_page(
    AsyncMock(),
    uuid4(),
    page=1,
    size=20,
  )

  assert execute_page.await_args.kwargs["order"] == SortOrder.DESC
