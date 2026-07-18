"""Public and citizen-owned ticket endpoints."""

from __future__ import annotations

import uuid
from typing import Optional, Tuple

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user, get_optional_current_user, role_required
from src.core.database import get_db
from src.core.filters import SortOrder, get_bbox_filter
from src.core.query_params import (
  DateRangeParams,
  PageParams,
  SearchParams,
  get_created_date_range,
  get_page_params,
  get_search_params,
)
from src.core.schemas import PaginatedResponse
from src.ticket.domain import TicketCategory, TicketStatus
from src.ticket.models import TicketSortField
from src.ticket.schemas import (
  TicketCancelRequest,
  TicketCitizenResponseRequest,
  TicketCreateRequest,
  TicketResponse,
  TicketStatusResponse,
  TicketUpdateRequest,
)
from src.ticket.services.mapper import TicketResponseMapper
from src.ticket.services.ticket_commands import TicketCommandService
from src.ticket.services.ticket_queries import TicketQueryService
from src.ticket.services.workflow_commands import TicketWorkflowCommandService
from src.user.models import Role, User


router = APIRouter()


@router.get("", response_model=PaginatedResponse[TicketResponse])
async def list_public_tickets(
  office_id: uuid.UUID | None = Query(None),
  category: TicketCategory | None = Query(None),
  bbox: Optional[Tuple[float, float, float, float]] = Depends(get_bbox_filter),
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  sort_by: TicketSortField = Query(TicketSortField.CREATED_AT),
  order: SortOrder = SortOrder.DESC,
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  created_range: DateRangeParams = Depends(get_created_date_range),
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """List public community tickets using shared validated query parameters."""

  return await TicketQueryService.list_public_tickets(
    db,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
    office_id=office_id,
    category=category,
    status=ticket_status,
    created_from=created_range.start,
    created_to=created_range.end,
    bbox=bbox,
    search=search_params.q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/mine", response_model=PaginatedResponse[TicketResponse])
async def list_my_tickets(
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  category: TicketCategory | None = Query(None),
  sort_by: TicketSortField = Query(TicketSortField.CREATED_AT),
  order: SortOrder = SortOrder.DESC,
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
):
  """List all public and private tickets created by the current user."""

  return await TicketQueryService.list_my_tickets(
    db,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
    status=ticket_status,
    category=category,
    search=search_params.q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Return a public ticket or a private ticket visible to the caller."""

  return await TicketQueryService.get_ticket(db, ticket_id, current_user)


@router.get("/{ticket_id}/status", response_model=list[TicketStatusResponse])
async def get_ticket_status_history(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Return the reduced citizen-facing status history."""

  return await TicketQueryService.get_status_history(db, ticket_id, current_user)


@router.get(
  "/{ticket_id}/status/current",
  response_model=TicketStatusResponse | None,
)
async def get_current_ticket_status(
  ticket_id: uuid.UUID,
  response: Response,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Return the latest citizen-facing status or HTTP 204 if none exists."""

  current = await TicketQueryService.get_current_status(db, ticket_id, current_user)
  if current is None:
    response.status_code = status.HTTP_204_NO_CONTENT
  return current


@router.post("/{ticket_id}/response", response_model=TicketResponse)
async def respond_to_ticket_question(
  ticket_id: uuid.UUID,
  request: TicketCitizenResponseRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Let the ticket creator answer the currently pending authority question."""

  ticket, event = await TicketWorkflowCommandService.respond_as_citizen(
    db, ticket_id, request, current_user
  )
  return TicketResponseMapper.to_public_ticket(
    ticket,
    current_status_event=event,
    current_user=current_user,
  )


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
  request: TicketCreateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Submit a ticket to the dispatcher inbox without an office selection."""

  return await TicketCommandService.create_ticket(db, request, current_user)


@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
  ticket_id: uuid.UUID,
  request: TicketUpdateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Update a citizen ticket before it has been dispatched."""

  return await TicketCommandService.update_ticket(db, ticket_id, request, current_user)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ticket(
  ticket_id: uuid.UUID,
  request: TicketCancelRequest = Body(default_factory=TicketCancelRequest),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Cancel a ticket while it is still waiting in the central inbox."""

  await TicketCommandService.cancel_ticket(db, ticket_id, request, current_user)
