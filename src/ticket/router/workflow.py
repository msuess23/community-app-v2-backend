"""Authority-side ticket workflow endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import role_required
from src.core.database import get_db
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.ticket.domain import TicketCategory, TicketStatus, TicketWorkflowState
from src.ticket.models import TicketSortField
from src.ticket.schemas import (
  PrimaryOfficerAssignmentRequest,
  TicketDispatchRequest,
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketInternalResponse,
  TicketWorkflowRequest,
)
from src.ticket.services.workflow_commands import TicketWorkflowCommandService
from src.ticket.services.workflow_queries import TicketWorkflowQueryService
from src.user.models import Role, User


router = APIRouter()


@router.get("/work-queue", response_model=PaginatedResponse[TicketInternalResponse])
async def list_ticket_work_queue(
  workflow_state: TicketWorkflowState | None = Query(None),
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  category: TicketCategory | None = Query(None),
  q: str | None = Query(None, max_length=200),
  page: int = Query(1, ge=1),
  size: int = Query(20, ge=1, le=100),
  sort_by: TicketSortField = Query(TicketSortField.UPDATED_AT),
  order: SortOrder = SortOrder.DESC,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Return the role-scoped queue used by the authority client."""

  return await TicketWorkflowQueryService.list_work_queue(
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


@router.get("/{ticket_id}/internal", response_model=TicketInternalDetailResponse)
async def get_internal_ticket(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Return workflow fields and the commands currently available."""

  return await TicketWorkflowQueryService.get_internal_ticket(db, ticket_id, current_user)


@router.get("/{ticket_id}/events", response_model=list[TicketEventResponse])
async def get_internal_ticket_events(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.DISPATCHER, Role.OFFICER, Role.MANAGER)
  ),
):
  """Return the complete append-only event stream to authorized staff."""

  return await TicketWorkflowQueryService.get_internal_events(db, ticket_id, current_user)


@router.post("/{ticket_id}/dispatch", response_model=TicketInternalDetailResponse)
async def dispatch_ticket(
  ticket_id: uuid.UUID,
  request: TicketDispatchRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.DISPATCHER)),
):
  """Route a central-inbox ticket to one active office."""

  ticket = await TicketWorkflowCommandService.dispatch_ticket(
    db, ticket_id, request, current_user
  )
  return await TicketWorkflowQueryService.internal_detail_response(
    db, ticket, current_user
  )


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
  """Assign the permanent officer after the ticket reaches an office."""

  ticket = await TicketWorkflowCommandService.assign_primary_officer(
    db, ticket_id, request, current_user
  )
  return await TicketWorkflowQueryService.internal_detail_response(
    db, ticket, current_user
  )


@router.post("/{ticket_id}/workflow", response_model=TicketInternalDetailResponse)
async def execute_ticket_workflow(
  ticket_id: uuid.UUID,
  request: TicketWorkflowRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.OFFICER, Role.MANAGER)),
):
  """Execute one validated sequential ad-hoc workflow command."""

  ticket = await TicketWorkflowCommandService.execute_workflow(
    db, ticket_id, request, current_user
  )
  return await TicketWorkflowQueryService.internal_detail_response(
    db, ticket, current_user
  )
