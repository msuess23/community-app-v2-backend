"""Append-only comments and community vote endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user, get_optional_current_user, role_required
from src.core.database import get_db
from src.ticket.comment_service import TicketCommentService
from src.ticket.schemas import (
  TicketCommentCreateRequest, TicketCommentResponse,
  TicketVoteResponse,
)
from src.ticket.vote_service import TicketVoteService
from src.user.models import Role, User


router = APIRouter()

@router.get("/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_ticket_comments(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Returns public comments and internal notes visible to the caller."""

  return await TicketCommentService.list_comments(db, ticket_id, current_user)


@router.post(
  "/{ticket_id}/comments",
  response_model=TicketCommentResponse,
  status_code=status.HTTP_201_CREATED,
)
async def add_ticket_comment(
  ticket_id: uuid.UUID,
  request: TicketCommentCreateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
):
  """Appends an immutable citizen-visible comment or internal staff note."""

  return await TicketCommentService.add_comment(db, ticket_id, request, current_user)


@router.get("/{ticket_id}/vote", response_model=TicketVoteResponse)
async def get_ticket_vote_summary(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Returns the community vote count and caller-specific vote state."""

  return await TicketVoteService.get_summary(db, ticket_id, current_user)


@router.post("/{ticket_id}/vote", response_model=TicketVoteResponse)
async def vote_for_ticket(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Adds one citizen vote to a public ticket."""

  return await TicketVoteService.add_vote(db, ticket_id, current_user)


@router.delete("/{ticket_id}/vote", response_model=TicketVoteResponse)
async def remove_ticket_vote(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Removes the current citizen's vote from a public ticket."""

  return await TicketVoteService.remove_vote(db, ticket_id, current_user)
