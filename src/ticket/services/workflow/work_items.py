"""Commands for bounded parallel cosignature work items."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictException, ForbiddenException, ResourceNotFoundException, WorkflowValidationException
from src.ticket.events import (
  ParallelWorkItemRequest, ParallelWorkItemsRequestedPayload, TicketEventType, TicketWorkflowState, TicketWorkItemKind, TicketWorkItemStatus,
  WorkItemCancelledPayload, WorkItemCompletedPayload,
)
from src.ticket.models import TicketWorkItem
from src.ticket.repository import TicketRepository
from src.ticket.schemas import (
  CancelWorkItemAction, CompleteWorkItemAction,
  RequestParallelCosignaturesAction, TicketInternalDetailResponse,
)
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket, require_work_item_for_update
from src.ticket.services.workflow.rules import require_active_staff, require_current_coordinator, require_no_blocking_tasks
from src.user.models import User

from src.ticket.services.workflow.queries import TicketWorkflowQueryService


class TicketWorkItemService:
  """Creates, completes and cancels projected parallel workflow tasks."""

  @staticmethod
  async def request_parallel_cosignatures(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: RequestParallelCosignaturesAction,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Creates one non-nested parallel cosignature round."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)
    if ticket.workflow_state != TicketWorkflowState.IN_PROGRESS:
      raise WorkflowValidationException(
        "Parallel cosignatures require a ticket in active processing."
      )
    await require_no_blocking_tasks(db, ticket)

    assignees: list[User] = []
    for assignee_id in request.assignee_user_ids:
      assignee = await require_active_staff(db, assignee_id)
      if assignee.id == current_user.id:
        raise WorkflowValidationException("A user cannot request their own cosignature.")
      assignees.append(assignee)

    group_id = uuid.uuid4()
    payload = ParallelWorkItemsRequestedPayload(
      group_id=group_id,
      return_to_user_id=current_user.id,
      items=[
        ParallelWorkItemRequest(
          assignee_user_id=assignee.id,
          kind=TicketWorkItemKind.COSIGNATURE,
          comment=request.comment,
          is_blocking=True,
        )
        for assignee in assignees
      ],
    )
    event = await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.PARALLEL_WORK_ITEMS_REQUESTED,
      payload=payload,
    )

    # Work items are a query projection. The immutable request event remains the
    # source of truth and contains the same assignee set and shared group ID.
    for item in payload.items:
      TicketRepository.add_work_item(
        db,
        TicketWorkItem(
          id=uuid.uuid4(),
          ticket_id=ticket.id,
          group_id=payload.group_id,
          kind=item.kind,
          status=TicketWorkItemStatus.OPEN,
          assignee_user_id=item.assignee_user_id,
          requested_by_user_id=current_user.id,
          return_to_user_id=payload.return_to_user_id,
          requested_event_id=event.id,
          is_blocking=item.is_blocking,
          comment=item.comment,
          created_at=event.occurred_at,
        ),
      )
    await db.flush()
    return await TicketWorkflowQueryService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def complete_work_item(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CompleteWorkItemAction,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Completes one task while sibling tasks remain independently open."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    work_item = await require_work_item_for_update(db, request.work_item_id)
    if work_item.ticket_id != ticket.id:
      raise ResourceNotFoundException(
        "Work item not found",
        error_code="TICKET_WORK_ITEM_NOT_FOUND",
      )
    if work_item.assignee_user_id != current_user.id:
      raise ForbiddenException("Only the assigned user may complete this work item")
    if work_item.status != TicketWorkItemStatus.OPEN:
      raise ConflictException(
        "The work item has already been completed or cancelled.",
        error_code="TICKET_WORK_ITEM_CLOSED",
      )
    if ticket.workflow_state == TicketWorkflowState.COMPLETED:
      raise WorkflowValidationException("A completed ticket cannot accept task results.")

    completed_at = datetime.now(timezone.utc)
    event = await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.WORK_ITEM_COMPLETED,
      payload=WorkItemCompletedPayload(
        work_item_id=work_item.id,
        outcome=request.outcome,
        comment=request.comment,
      ),
      occurred_at=completed_at,
    )
    work_item.status = TicketWorkItemStatus.COMPLETED
    work_item.outcome = request.outcome
    work_item.completed_event_id = event.id
    work_item.completed_at = completed_at
    await db.flush()

    # Parallel assignees complete only their own task. The current responsible
    # user remains the coordinator of the complete ticket workflow.
    return await TicketWorkflowQueryService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def cancel_work_item(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CancelWorkItemAction,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Cancels one open task without modifying completed sibling tasks."""

    ticket = await require_ticket(db, ticket_id, for_update=True)
    require_current_coordinator(ticket, current_user)

    work_item = await require_work_item_for_update(db, request.work_item_id)
    if work_item.ticket_id != ticket.id:
      raise ResourceNotFoundException(
        "Work item not found",
        error_code="TICKET_WORK_ITEM_NOT_FOUND",
      )
    if work_item.requested_by_user_id != current_user.id:
      raise ForbiddenException("Only the task requester may cancel this work item")
    if work_item.status != TicketWorkItemStatus.OPEN:
      raise ConflictException(
        "The work item has already been completed or cancelled.",
        error_code="TICKET_WORK_ITEM_CLOSED",
      )

    cancelled_at = datetime.now(timezone.utc)
    event = await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.WORK_ITEM_CANCELLED,
      payload=WorkItemCancelledPayload(
        work_item_id=work_item.id,
        reason=request.reason,
      ),
      occurred_at=cancelled_at,
    )
    work_item.status = TicketWorkItemStatus.CANCELLED
    work_item.completed_event_id = event.id
    work_item.completed_at = cancelled_at
    await db.flush()
    return await TicketWorkflowQueryService._internal_detail_response(
      db,
      ticket,
      current_user,
    )
