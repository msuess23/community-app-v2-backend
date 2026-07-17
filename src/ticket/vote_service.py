"""Community vote operations for public tickets."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, ForbiddenException, ResourceNotFoundException
from src.ticket.events import TicketVisibility
from src.ticket.models import TicketVote
from src.ticket.repository import TicketRepository
from src.ticket.schemas import TicketVoteResponse
from src.ticket.service import TicketService
from src.user.models import Role, User


class TicketVoteService:
  """Maintains relational votes without mixing them into the case workflow."""

  @staticmethod
  async def _visible_public_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ):
    """Loads one visible public ticket that can participate in voting."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketService._can_view_ticket(db, ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    if ticket.visibility != TicketVisibility.PUBLIC:
      raise ConflictException(
        "Private tickets cannot receive community votes.",
        error_code="PRIVATE_TICKET_NOT_VOTABLE",
      )
    return ticket

  @staticmethod
  async def get_summary(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> TicketVoteResponse:
    """Returns the vote count and the optional caller-specific vote state."""

    ticket = await TicketVoteService._visible_public_ticket(
      db,
      ticket_id,
      current_user,
    )
    user_voted = None
    if current_user is not None:
      user_voted = any(vote.user_id == current_user.id for vote in ticket.votes)
    return TicketVoteResponse(
      ticket_id=ticket.id,
      votes_count=len(ticket.votes),
      user_voted=user_voted,
    )

  @staticmethod
  async def add_vote(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketVoteResponse:
    """Adds one idempotency-protected citizen vote to a public ticket."""

    if current_user.role != Role.CITIZEN:
      raise ForbiddenException("Only citizens may vote for community tickets")
    ticket = await TicketVoteService._visible_public_ticket(db, ticket_id, current_user)
    if any(vote.user_id == current_user.id for vote in ticket.votes):
      raise ConflictException(
        "The user has already voted for this ticket.",
        error_code="TICKET_ALREADY_VOTED",
      )

    vote = TicketVote(
      id=uuid.uuid4(),
      ticket_id=ticket.id,
      user_id=current_user.id,
    )
    TicketRepository.add_vote(db, vote)
    await db.flush()
    ticket.votes.append(vote)
    return TicketVoteResponse(
      ticket_id=ticket.id,
      votes_count=len(ticket.votes),
      user_voted=True,
    )

  @staticmethod
  async def remove_vote(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketVoteResponse:
    """Removes the current citizen's vote if it exists."""

    if current_user.role != Role.CITIZEN:
      raise ForbiddenException("Only citizens may vote for community tickets")
    ticket = await TicketVoteService._visible_public_ticket(db, ticket_id, current_user)
    vote = next(
      (item for item in ticket.votes if item.user_id == current_user.id),
      None,
    )
    if vote is not None:
      await db.delete(vote)
      await db.flush()
      ticket.votes.remove(vote)

    return TicketVoteResponse(
      ticket_id=ticket.id,
      votes_count=len(ticket.votes),
      user_voted=False,
    )
