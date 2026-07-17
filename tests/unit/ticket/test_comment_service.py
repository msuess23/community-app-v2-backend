from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import ForbiddenException
from src.ticket.comment_service import TicketCommentService
from src.ticket.events import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import TicketCommentCreateRequest
from src.user.models import Role, User


def _user(role: Role, *, office_id: UUID | None = None) -> User:
  return User(
    id=uuid4(),
    email=f"{uuid4()}@example.com",
    hashed_password="hash",
    first_name="Test",
    last_name=role.value,
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _ticket(creator_id: UUID, *, office_id: UUID | None = None) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid4(),
    title="Pothole",
    description="Deep road damage",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=creator_id,
    office_id=office_id,
    visibility=TicketVisibility.PUBLIC,
    public_status=TicketStatus.IN_PROGRESS,
    public_status_message="In progress",
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    version=3,
    created_at=now,
    updated_at=now,
  )


@pytest.mark.asyncio
async def test_citizen_cannot_create_internal_comment(monkeypatch) -> None:
  citizen = _user(Role.CITIZEN)
  ticket = _ticket(citizen.id)
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )

  with pytest.raises(ForbiddenException):
    await TicketCommentService.add_comment(
      AsyncMock(),
      ticket.id,
      TicketCommentCreateRequest(text="Hidden note", isInternal=True),
      citizen,
    )


@pytest.mark.asyncio
async def test_external_comment_is_append_only_and_citizen_visible(monkeypatch) -> None:
  citizen = _user(Role.CITIZEN)
  ticket = _ticket(citizen.id)
  staged_events: list[TicketEvent] = []
  db = AsyncMock()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, event: staged_events.append(event),
  )

  response = await TicketCommentService.add_comment(
    db,
    ticket.id,
    TicketCommentCreateRequest(text="The damage became larger"),
    citizen,
  )

  assert response.text == "The damage became larger"
  assert response.is_internal is False
  assert staged_events[-1].event_type == TicketEventType.TICKET_COMMENTED
  assert ticket.version == 4


@pytest.mark.asyncio
async def test_public_comment_list_filters_internal_staff_notes(monkeypatch) -> None:
  citizen = _user(Role.CITIZEN)
  ticket = _ticket(citizen.id)
  now = datetime.now(timezone.utc)
  public_event = TicketEvent(
    id=uuid4(),
    ticket_id=ticket.id,
    sequence_number=4,
    event_type=TicketEventType.TICKET_COMMENTED,
    actor_user_id=citizen.id,
    occurred_at=now,
    payload={"text": "Public update", "is_internal": False},
  )
  internal_event = TicketEvent(
    id=uuid4(),
    ticket_id=ticket.id,
    sequence_number=5,
    event_type=TicketEventType.TICKET_COMMENTED,
    actor_user_id=uuid4(),
    occurred_at=now,
    payload={"text": "Internal note", "is_internal": True},
  )

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_comment_events",
    AsyncMock(return_value=[public_event, internal_event]),
  )

  comments = await TicketCommentService.list_comments(
    AsyncMock(),
    ticket.id,
    citizen,
  )

  assert [comment.text for comment in comments] == ["Public update"]
