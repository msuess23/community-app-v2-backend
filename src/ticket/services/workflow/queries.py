"""Authority-side work queues, details, events and allowed actions."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, ResourceNotFoundException
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.ticket.events import (
  TicketCategory,
  TicketStatus,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketSortField
from src.ticket.repository import TicketRepository
from src.ticket.schemas import (
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketInternalResponse,
)
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketResponseMapper
from src.ticket.services.timeline import latest_status_events
from src.ticket.services.workflow.rules import STAFF_ROLES
from src.user.models import Role, User


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
      and ticket.primary_officer_id is None
      and ticket.workflow_state == TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
    ):
      actions.append(TicketWorkflowAction.ASSIGN_PRIMARY_OFFICER)

    is_coordinator = (
      current_user.role in STAFF_ROLES
      and ticket.current_responsible_user_id == current_user.id
    )
    if is_coordinator and ticket.workflow_state == TicketWorkflowState.IN_PROGRESS:
      actions.extend(
        [
          TicketWorkflowAction.FORWARD,
          TicketWorkflowAction.REQUEST_COSIGNATURE,
          TicketWorkflowAction.ESCALATE,
          TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
          TicketWorkflowAction.COMPLETE,
        ]
      )

    if (
      is_coordinator
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_COSIGNATURE
      and ticket.pending_return_to_user_id is not None
    ):
      actions.append(TicketWorkflowAction.COSIGN)

    if (
      current_user.role == Role.MANAGER
      and ticket.current_responsible_user_id == current_user.id
      and ticket.workflow_state == TicketWorkflowState.WAITING_FOR_DECISION
      and ticket.pending_return_to_user_id is not None
    ):
      actions.append(TicketWorkflowAction.DECIDE_ESCALATION)

    return actions

  @staticmethod
  async def _internal_detail_response(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Build one internal detail including server-computed actions."""

    latest = latest_status_events(await TicketRepository.get_events(db, ticket.id))
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
    """List the role-scoped administrative work queue."""

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
    latest = latest_status_events(
      await TicketRepository.get_events_for_tickets(db, [ticket.id for ticket in tickets])
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

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view_internal(
      db, ticket, current_user
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowQueryService._internal_detail_response(
      db, ticket, current_user
    )

  @staticmethod
  async def get_internal_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> list[TicketEventResponse]:
    """Return the complete chronological event stream to authorized staff."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view_internal(
      db, ticket, current_user
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return [
      TicketResponseMapper.to_event(event)
      for event in await TicketRepository.get_events(db, ticket.id)
    ]
