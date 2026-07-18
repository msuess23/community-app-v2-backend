"""Authority-side ticket workflow endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import role_required
from src.core.database import get_db
from src.core.filters import SortOrder
from src.core.query_params import (
  PageParams,
  SearchParams,
  get_page_params,
  get_search_params,
)
from src.core.schemas import PaginatedResponse
from src.ticket.domain.enums import TicketCategory, TicketStatus, TicketWorkflowState
from src.ticket.models.ticket import TicketSortField
from src.ticket.schemas.workflow import (
  PrimaryOfficerAssignmentRequest,
  TicketDispatchRequest,
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketWorkflowRequest,
)
from src.ticket.schemas.ticket import TicketInternalResponse
from src.ticket.services.workflow_commands import TicketWorkflowCommandService
from src.ticket.services.workflow_queries import TicketWorkflowQueryService
from src.user.models import Role, User
from src.user.roles import AUTHORITY_ROLES, CASE_WORKER_ROLES


router = APIRouter()


@router.get("/work-queue", response_model=PaginatedResponse[TicketInternalResponse])
async def list_ticket_work_queue(
  workflow_state: TicketWorkflowState | None = Query(None),
  ticket_status: TicketStatus | None = Query(None, alias="status"),
  category: TicketCategory | None = Query(None),
  sort_by: TicketSortField = Query(TicketSortField.UPDATED_AT),
  order: SortOrder = SortOrder.DESC,
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(*AUTHORITY_ROLES)),
):
  """Return the role-scoped queue used by the authority client."""

  return await TicketWorkflowQueryService.list_work_queue(
    db,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
    workflow_state=workflow_state,
    status=ticket_status,
    category=category,
    search=search_params.q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/{ticket_id}/internal", response_model=TicketInternalDetailResponse)
async def get_internal_ticket(
  ticket_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(*AUTHORITY_ROLES)),
):
  """Return workflow fields and the commands currently available."""

  return await TicketWorkflowQueryService.get_internal_ticket(db, ticket_id, current_user)


@router.get(
  "/{ticket_id}/events",
  response_model=PaginatedResponse[TicketEventResponse],
)
async def get_internal_ticket_events(
  ticket_id: uuid.UUID,
  page_params: PageParams = Depends(get_page_params),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(*AUTHORITY_ROLES)),
):
  """Return a chronological page of the append-only event stream."""

  return await TicketWorkflowQueryService.get_internal_events(
    db,
    ticket_id,
    current_user,
    page=page_params.page,
    size=page_params.size,
  )


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
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Execute one validated sequential ad-hoc workflow command."""

  ticket = await TicketWorkflowCommandService.execute_workflow(
    db, ticket_id, request, current_user
  )
  return await TicketWorkflowQueryService.internal_detail_response(
    db, ticket, current_user
  )
