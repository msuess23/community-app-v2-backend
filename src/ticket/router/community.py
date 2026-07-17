"""Append-only ticket comment endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user, get_optional_current_user
from src.core.database import get_db
from src.ticket.comment_service import TicketCommentService
from src.ticket.schemas import TicketCommentCreateRequest, TicketCommentResponse
from src.user.models import User


router = APIRouter()


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentResponse])
async def list_ticket_comments(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Return public comments and internal notes visible to the caller."""

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
  """Append an immutable public comment or internal staff note."""

  return await TicketCommentService.add_comment(db, ticket_id, request, current_user)
