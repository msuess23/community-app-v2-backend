"""HTTP endpoints for citizen ticket submission and public ticket queries."""

import uuid
from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import (
  get_current_user,
  get_optional_current_user,
  role_required,
)
from src.core.database import get_db
from src.core.filters import SortOrder, get_bbox_filter
from src.core.schemas import PaginatedResponse
from src.ticket.events import TicketCategory, TicketStatus, TicketWorkflowState
from src.ticket.models import TicketSortField
from src.ticket.schemas import (
  PrimaryOfficerAssignmentRequest,
  TicketAllowedActionsResponse,
  TicketCancelRequest,
  TicketCreateRequest,
  TicketDispatchRequest,
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketInternalResponse,
  TicketResponse,
  TicketStatusResponse,
  TicketUpdateRequest,
  TicketWorkflowRequest,
)
from src.ticket.service import TicketService
from src.ticket.workflow_service import TicketWorkflowService
from src.user.models import Role, User


router = APIRouter()


@router.get("", response_model=PaginatedResponse[TicketResponse])
async def list_public_tickets(
  office_id: uuid.UUID | None = Query(None, alias="officeId"),
  category: TicketCategory | None = Query(None),
  created_from: datetime | None = Query(None, alias="createdFrom"),
  created_to: datetime | None = Query(None, alias="createdTo"),
  bbox: Optional[Tuple[float, float, float, float]] = Depends(get_bbox_filter),
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  q: str | None = Query(None, max_length=200),
  page: int = Query(1, ge=1),
  size: int = Query(20, ge=1, le=100),
  sort_by: TicketSortField = Query(TicketSortField.CREATED_AT, alias="sortBy"),
  order: SortOrder = SortOrder.DESC,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Lists public community tickets using the former Ktor filter names."""

  return await TicketService.list_public_tickets(
    db,
    current_user=current_user,
    page=page,
    size=size,
    office_id=office_id,
    category=category,
    status=ticket_status,
    created_from=created_from,
    created_to=created_to,
    bbox=bbox,
    search=q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/mine", response_model=PaginatedResponse[TicketResponse])
async def list_my_tickets(
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  category: TicketCategory | None = Query(None),
  q: str | None = Query(None, max_length=200),
  page: int = Query(1, ge=1),
  size: int = Query(20, ge=1, le=100),
  sort_by: TicketSortField = Query(TicketSortField.CREATED_AT, alias="sortBy"),
  order: SortOrder = SortOrder.DESC,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_user),
):
  """Lists all public and private tickets created by the current user."""

  return await TicketService.list_my_tickets(
    db,
    current_user=current_user,
    page=page,
    size=size,
    status=ticket_status,
    category=category,
    search=q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/work-queue", response_model=PaginatedResponse[TicketInternalResponse])
async def list_ticket_work_queue(
  workflow_state: TicketWorkflowState | None = Query(None, alias="workflowState"),
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  category: TicketCategory | None = Query(None),
  q: str | None = Query(None, max_length=200),
  page: int = Query(1, ge=1),
  size: int = Query(20, ge=1, le=100),
  sort_by: TicketSortField = Query(TicketSortField.UPDATED_AT, alias="sortBy"),
  order: SortOrder = SortOrder.DESC,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Returns the role-scoped queue used by the administrative client."""

  return await TicketWorkflowService.list_work_queue(
    db,
    current_user=current_user,
    page=page,
    size=size,
    workflow_state=workflow_state,
    status=ticket_status,
    category=category,
    search=q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Returns a public ticket or a private ticket visible to the caller."""

  return await TicketService.get_ticket(db, ticket_id, current_user)


@router.get("/{ticket_id}/status", response_model=list[TicketStatusResponse])
async def get_ticket_status_history(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User | None = Depends(get_optional_current_user),
):
  """Returns the reduced citizen-facing status history."""

  return await TicketService.get_status_history(db, ticket_id, current_user)


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
  """Returns the latest citizen-facing status or HTTP 204 if none exists."""

  current = await TicketService.get_current_status(db, ticket_id, current_user)
  if current is None:
    response.status_code = status.HTTP_204_NO_CONTENT
  return current


@router.get("/{ticket_id}/internal", response_model=TicketInternalDetailResponse)
async def get_internal_ticket(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Returns workflow fields, parallel tasks and server-computed actions."""

  return await TicketWorkflowService.get_internal_ticket(db, ticket_id, current_user)


@router.get("/{ticket_id}/events", response_model=list[TicketEventResponse])
async def get_internal_ticket_events(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Returns the complete append-only event stream to authorized staff."""

  return await TicketWorkflowService.get_internal_events(db, ticket_id, current_user)


@router.get(
  "/{ticket_id}/allowed-actions",
  response_model=TicketAllowedActionsResponse,
)
async def get_allowed_ticket_actions(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Returns the workflow commands currently available to this staff user."""

  return await TicketWorkflowService.get_allowed_actions(db, ticket_id, current_user)


@router.post("/{ticket_id}/dispatch", response_model=TicketInternalDetailResponse)
async def dispatch_ticket(
  ticket_id: uuid.UUID,
  request: TicketDispatchRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.DISPATCHER)),
):
  """Routes a central-inbox ticket to one active office."""

  return await TicketWorkflowService.dispatch_ticket(db, ticket_id, request, current_user)


@router.post(
  "/{ticket_id}/primary-officer",
  response_model=TicketInternalDetailResponse,
)
async def assign_primary_officer(
  ticket_id: uuid.UUID,
  request: PrimaryOfficerAssignmentRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.MANAGER)),
):
  """Assigns the permanent officer after the ticket reaches an office."""

  return await TicketWorkflowService.assign_primary_officer(
    db,
    ticket_id,
    request,
    current_user,
  )


@router.post("/{ticket_id}/workflow", response_model=TicketInternalDetailResponse)
async def execute_ticket_workflow(
  ticket_id: uuid.UUID,
  request: TicketWorkflowRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.OFFICER, Role.MANAGER)),
):
  """Executes a validated ad-hoc workflow command."""

  return await TicketWorkflowService.execute_workflow(db, ticket_id, request, current_user)


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
  request: TicketCreateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Submits a ticket to the dispatcher inbox without an office selection."""

  return await TicketService.create_ticket(db, request, current_user)


@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
  ticket_id: uuid.UUID,
  request: TicketUpdateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Updates a citizen ticket before it has been dispatched."""

  return await TicketService.update_ticket(db, ticket_id, request, current_user)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_ticket(
  ticket_id: uuid.UUID,
  request: TicketCancelRequest = Body(default_factory=TicketCancelRequest),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Cancels a ticket while it is still waiting in the central inbox."""

  await TicketService.cancel_ticket(db, ticket_id, request, current_user)
