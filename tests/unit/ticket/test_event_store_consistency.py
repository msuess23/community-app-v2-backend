from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.ticket.domain import (
  TicketCategory,
  TicketCommentedPayload,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.ticket.services.errors import TicketProjectionVersionMismatchException
from src.ticket.services.event_store import TicketEventStore


@pytest.mark.asyncio
async def test_append_rejects_projection_that_does_not_match_event_stream(monkeypatch) -> None:
  now = datetime.now(timezone.utc)
  ticket = Ticket(
    id=uuid4(),
    title="Pothole",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=uuid4(),
    visibility=TicketVisibility.PUBLIC,
    public_status=TicketStatus.OPEN,
    workflow_state=TicketWorkflowState.NEW,
    version=3,
    created_at=now,
    updated_at=now,
  )
  add_projection = AsyncMock()
  add_event = AsyncMock()
  monkeypatch.setattr(
    "src.ticket.repositories.event.TicketEventRepository.get_last_sequence_number",
    AsyncMock(return_value=2),
  )
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.add",
    add_projection,
  )
  monkeypatch.setattr(
    "src.ticket.repositories.event.TicketEventRepository.add_event",
    add_event,
  )

  with pytest.raises(TicketProjectionVersionMismatchException) as exc_info:
    await TicketEventStore.append(
      AsyncMock(),
      ticket,
      actor_user_id=uuid4(),
      event_type=TicketEventType.TICKET_COMMENTED,
      payload=TicketCommentedPayload(text="Note", is_internal=True),
    )

  assert exc_info.value.error_code == "TICKET_PROJECTION_VERSION_MISMATCH"
  add_projection.assert_not_called()
  add_event.assert_not_called()
  assert ticket.version == 3
