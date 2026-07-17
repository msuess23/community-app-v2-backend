"""Authority-side work queues, details, events and allowed actions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, ResourceNotFoundException
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.ticket.events import (
  TicketCategory, TicketStatus,
  TicketWorkflowAction, TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketSortField
from src.ticket.repository import TicketRepository
from src.ticket.schemas import (
  TicketAllowedActionsResponse,
  TicketEventResponse,
  TicketInternalDetailResponse, TicketInternalResponse,
)
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketResponseMapper
from src.ticket.services.workflow.rules import STAFF_ROLES
from src.user.models import Role, User

class TicketWorkflowQueryService:
  """Serves administrative workflow views without mutating the aggregate."""

  @staticmethod
  async def _allowed_actions(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> TicketAllowedActionsResponse:
    """Calculates server-side workflow commands for the authority client."""

    actions: list[TicketWorkflowAction] = []
    completable_ids = await TicketRepository.get_open_work_item_ids_for_user(
      db,
      ticket.id,
      current_user.id,
    )
    cancellable_ids = await TicketRepository.get_open_requested_work_item_ids(
      db,
      ticket.id,
      current_user.id,
    )

    if (
      current_user.role == Role.DISPATCHER
      and ticket.primary_officer_id is None
      and ticket.workflow_state
      in {
        TicketWorkflowState.NEW,
        TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
      }
    ):
      actions.append(TicketWorkflowAction.DISPATCH)

    if (
      current_user.role == Role.MANAGER
      and current_user.office_id is not None
      and current_user.office_id == ticket.office_id
      and ticket.primary_officer_id is None
      and ticket.workflow_state == TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
    ):
      actions.append(TicketWorkflowAction.ASSIGN_PRIMARY_OFFICER)

    is_coordinator = (
      current_user.role in STAFF_ROLES
      and ticket.current_responsible_user_id == current_user.id
    )
    has_blocking_tasks = await TicketRepository.has_open_blocking_work_items(
      db,
      ticket.id,
    )
    has_any_tasks = await TicketRepository.has_open_work_items(db, ticket.id)

    if is_coordinator and ticket.workflow_state == TicketWorkflowState.IN_PROGRESS:
      if not has_blocking_tasks:
        actions.extend(
          [
            TicketWorkflowAction.FORWARD,
            TicketWorkflowAction.REQUEST_PARALLEL_COSIGNATURES,
            TicketWorkflowAction.ESCALATE,
            TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
          ]
        )
      if not has_any_tasks:
        actions.append(TicketWorkflowAction.RESOLVE)
        if current_user.role == Role.MANAGER:
          actions.append(TicketWorkflowAction.REJECT_TICKET)

    if (
      current_user.role == Role.MANAGER
      and ticket.current_responsible_user_id == current_user.id
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_APPROVAL
      and ticket.pending_return_to_user_id is not None
    ):
      actions.extend(
        [
          TicketWorkflowAction.APPROVE_ESCALATION,
          TicketWorkflowAction.REJECT_ESCALATION,
        ]
      )

    if completable_ids:
      actions.append(TicketWorkflowAction.COMPLETE_WORK_ITEM)
    if cancellable_ids and ticket.current_responsible_user_id == current_user.id:
      actions.append(TicketWorkflowAction.CANCEL_WORK_ITEM)

    return TicketAllowedActionsResponse(
      actions=actions,
      completable_work_item_ids=completable_ids,
      cancellable_work_item_ids=cancellable_ids,
    )

  @staticmethod
  async def _internal_detail_response(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Builds one internal detail including tasks and computed actions."""

    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    internal = TicketResponseMapper.to_internal_ticket(
      ticket,
      current_status_event=latest.get(ticket.id),
      current_user=current_user,
    )
    work_items = await TicketRepository.get_work_items(db, ticket.id)
    allowed = await TicketWorkflowQueryService._allowed_actions(db, ticket, current_user)
    return TicketInternalDetailResponse(
      **internal.model_dump(),
      work_items=[
        TicketResponseMapper.to_work_item(item) for item in work_items
      ],
      allowed_actions=allowed,
    )

  @staticmethod
  async def list_work_queue(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    workflow_state: TicketWorkflowState | None = None,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.UPDATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> PaginatedResponse[TicketInternalResponse]:
    """Lists the role-scoped administrative work queue."""

    if current_user.role not in {Role.DISPATCHER, Role.OFFICER, Role.MANAGER}:
      raise ForbiddenException("This account has no ticket work queue")

    tickets, total = await TicketRepository.get_staff_page(
      db,
      current_user=current_user,
      page=page,
      size=size,
      workflow_state=workflow_state,
      status=status,
      category=category,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    latest_events = await TicketRepository.get_latest_public_events(
      db,
      [ticket.id for ticket in tickets],
    )
    data = [
      TicketResponseMapper.to_internal_ticket(
        ticket,
        current_status_event=latest_events.get(ticket.id),
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
    """Returns the workflow projection, tasks and available actions."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view_internal(
      db,
      ticket,
      current_user,
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowQueryService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def get_internal_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> list[TicketEventResponse]:
    """Returns the complete chronological event stream to authorized staff."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view_internal(
      db,
      ticket,
      current_user,
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events = await TicketRepository.get_events(db, ticket.id)
    return [TicketResponseMapper.to_event(event) for event in events]

  @staticmethod
  async def get_allowed_actions(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketAllowedActionsResponse:
    """Returns commands the staff client may currently offer to the user."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view_internal(
      db,
      ticket,
      current_user,
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowQueryService._allowed_actions(db, ticket, current_user)
