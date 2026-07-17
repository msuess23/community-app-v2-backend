from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import ConflictException
from src.ticket.events import TicketCategory, TicketVisibility, TicketWorkflowState
from src.ticket.models import Ticket, TicketVote
from src.ticket.vote_service import TicketVoteService
from src.user.models import Role, User


def _citizen() -> User:
  return User(
    id=uuid4(),
    email="voter@example.com",
    hashed_password="hash",
    first_name="Vote",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
  )


def _ticket() -> Ticket:
  return Ticket(
    id=uuid4(),
    title="Pothole",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=uuid4(),
    visibility=TicketVisibility.PUBLIC,
    workflow_state=TicketWorkflowState.NEW,
    votes=[],
    images=[],
  )


@pytest.mark.asyncio
async def test_vote_is_added_and_returned_in_summary(monkeypatch) -> None:
  db = AsyncMock()
  db.flush = AsyncMock()
  citizen = _citizen()
  ticket = _ticket()
  monkeypatch.setattr(
    "src.ticket.services.votes.TicketRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.services.votes.TicketAccessPolicy.can_view",
    AsyncMock(return_value=True),
  )
  monkeypatch.setattr(
    "src.ticket.services.votes.TicketRepository.add_vote",
    lambda _db, _vote: None,
  )

  response = await TicketVoteService.add_vote(db, ticket.id, citizen)

  assert response.votes_count == 1
  assert response.user_voted is True
  assert ticket.votes[0].user_id == citizen.id
  db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_duplicate_vote_is_rejected(monkeypatch) -> None:
  db = AsyncMock()
  citizen = _citizen()
  ticket = _ticket()
  ticket.votes.append(
    TicketVote(id=uuid4(), ticket_id=ticket.id, user_id=citizen.id)
  )
  monkeypatch.setattr(
    "src.ticket.services.votes.TicketRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.services.votes.TicketAccessPolicy.can_view",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as error:
    await TicketVoteService.add_vote(db, ticket.id, citizen)

  assert error.value.error_code == "TICKET_ALREADY_VOTED"
