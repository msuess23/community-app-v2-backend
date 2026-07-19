"""Authority-side work queues, details, events and allowed actions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, ResourceNotFoundException
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.ticket.domain import (
  TicketCategory,
  TicketLifecycleFilter,
  TicketStatus,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketSortField
from src.ticket.repositories.event import TicketEventRepository
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.schemas import (
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketInternalResponse,
)
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketResponseMapper
from src.ticket.services.timeline import latest_status_events
from src.user.models import Role, User
from src.user.roles import AUTHORITY_ROLES, CASE_WORKER_ROLES


class TicketWorkflowQueryService:
  """Serve administrative workflow views without mutating the aggregate."""

  @staticmethod
  def _allowed_actions(ticket: Ticket, current_user: User) -> list[TicketWorkflowAction]:
    """Calculate the small command set available to one staff user."""

    actions: list[TicketWorkflowAction] = []
    if (
      current_user.role == Role.DISPATCHER
      and ticket.primary_officer_id is None
      and ticket.workflow_state
      in {TicketWorkflowState.NEW, TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT}
    ):
      actions.append(TicketWorkflowAction.DISPATCH)

    if (
      current_user.role == Role.MANAGER
      and current_user.office_id == ticket.office_id
      and ticket.workflow_state != TicketWorkflowState.COMPLETED
    ):
      if (
        ticket.primary_officer_id is None
        and ticket.workflow_state == TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
      ):
        actions.append(TicketWorkflowAction.ASSIGN_PRIMARY_OFFICER)
      elif ticket.primary_officer_id is not None:
        actions.append(TicketWorkflowAction.REASSIGN_PRIMARY_OFFICER)

    is_assignee = (
      current_user.role in CASE_WORKER_ROLES
      and ticket.current_assignee_id == current_user.id
    )
    if is_assignee and ticket.workflow_state == TicketWorkflowState.IN_PROGRESS:
      actions.extend(
        [
          TicketWorkflowAction.FORWARD,
          TicketWorkflowAction.REQUEST_COSIGNATURE,
          TicketWorkflowAction.ESCALATE,
          TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
          TicketWorkflowAction.RETURN_TO_DISPATCH,
          TicketWorkflowAction.COMPLETE,
        ]
      )

    if (
      is_assignee
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_COSIGNATURE
      and ticket.return_to_user_id is not None
    ):
      actions.append(TicketWorkflowAction.COSIGN)

    if (
      current_user.role == Role.MANAGER
      and ticket.current_assignee_id == current_user.id
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_DECISION
      and ticket.return_to_user_id is not None
    ):
      actions.append(TicketWorkflowAction.DECIDE_ESCALATION)

    return actions

  @staticmethod
  async def internal_detail_response(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Build one internal detail including server-computed actions."""

    latest = latest_status_events(await TicketEventRepository.get_events(db, ticket.id))
    internal = TicketResponseMapper.to_internal_ticket(
      ticket,
      current_status_event=latest.get(ticket.id),
      current_user=current_user,
    )
    return TicketInternalDetailResponse(
      **internal.model_dump(),
      allowed_actions=TicketWorkflowQueryService._allowed_actions(ticket, current_user),
    )

  @staticmethod
  async def list_internal_tickets(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    lifecycle: TicketLifecycleFilter = TicketLifecycleFilter.ACTIVE,
    workflow_state: TicketWorkflowState | None = None,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    office_id: uuid.UUID | None = None,
    creator_user_id: uuid.UUID | None = None,
    primary_officer_id: uuid.UUID | None = None,
    current_assignee_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.UPDATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> PaginatedResponse[TicketInternalResponse]:
    """List role-scoped active tickets or the searchable authority archive."""

    if current_user.role not in AUTHORITY_ROLES:
      raise ForbiddenException("This account has no internal ticket access")

    tickets, total = await TicketProjectionRepository.get_staff_page(
      db,
      current_user=current_user,
      page=page,
      size=size,
      lifecycle=lifecycle,
      workflow_state=workflow_state,
      status=status,
      category=category,
      office_id=office_id,
      creator_user_id=creator_user_id,
      primary_officer_id=primary_officer_id,
      current_assignee_id=current_assignee_id,
      created_from=created_from,
      created_to=created_to,
      updated_from=updated_from,
      updated_to=updated_to,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    latest = latest_status_events(
      await TicketEventRepository.get_events_for_tickets(
        db,
        [ticket.id for ticket in tickets],
      )
    )
    data = [
      TicketResponseMapper.to_internal_ticket(
        ticket,
        current_status_event=latest.get(ticket.id),
        current_user=current_user,
      )
      for ticket in tickets
    ]
    return PaginatedResponse.create(data=data, total=total, page=page, size=size)

  @staticmethod
  async def get_internal_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Return the workflow projection and available actions."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or not TicketAccessPolicy.can_view_internal(ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowQueryService.internal_detail_response(
      db, ticket, current_user
    )

  @staticmethod
  async def get_internal_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
    *,
    page: int,
    size: int,
  ) -> PaginatedResponse[TicketEventResponse]:
    """Return a chronological page of events to authorized staff."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or not TicketAccessPolicy.can_view_internal(ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events, total = await TicketEventRepository.get_event_page(
      db,
      ticket.id,
      page=page,
      size=size,
    )
    return PaginatedResponse.create(
      data=[TicketResponseMapper.to_event(event) for event in events],
      total=total,
      page=page,
      size=size,
    )
