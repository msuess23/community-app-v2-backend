from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.ticket.events import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import TicketCreateRequest
from src.ticket.service import TicketService
from src.user.models import Role, User


@pytest.mark.asyncio
async def test_create_ticket_stages_projection_and_initial_event(monkeypatch) -> None:
  db = AsyncMock()
  db.flush = AsyncMock()
  staged: list[object] = []
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, entity: staged.append(entity),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, entity: staged.append(entity),
  )
  citizen = User(
    id=uuid4(),
    email="citizen@example.com",
    hashed_password="hash",
    first_name="Test",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
  )

  response = await TicketService.create_ticket(
    db,
    TicketCreateRequest(
      title="Pothole in Main Street",
      category=TicketCategory.INFRASTRUCTURE,
    ),
    citizen,
  )

  ticket = next(item for item in staged if isinstance(item, Ticket))
  event = next(item for item in staged if isinstance(item, TicketEvent))
  assert ticket.office_id is None
  assert ticket.workflow_state == TicketWorkflowState.NEW
  assert ticket.primary_officer_id is None
  assert ticket.current_responsible_user_id is None
  assert event.event_type == TicketEventType.TICKET_SUBMITTED
  assert event.sequence_number == 1
  assert ticket.public_status == TicketStatus.OPEN
  assert "office_id" not in event.payload
  assert response.office_id is None
  assert response.current_status is not None
  assert response.current_status.status == TicketStatus.OPEN
  db.flush.assert_awaited_once()


def test_ticket_response_locks_citizen_edits_after_processing_starts() -> None:
  citizen = User(
    id=uuid4(),
    email="locked@example.com",
    hashed_password="hash",
    first_name="Locked",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
  )
  ticket = Ticket(
    id=uuid4(),
    title="Already dispatched",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=citizen.id,
    workflow_state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    visibility=TicketVisibility.PUBLIC,
    created_at=datetime.now(timezone.utc),
    version=2,
    images=[],
  )

  response = TicketService._ticket_response(
    ticket,
    current_status_event=None,
    current_user=citizen,
  )

  assert response.can_edit is False
  assert response.can_manage_images is False
