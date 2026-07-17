"""Authority-side commands and queries for the ticket ad-hoc workflow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
  ConflictException,
  ForbiddenException,
  ResourceNotFoundException,
  WorkflowValidationException,
)
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.office.repository import OfficeRepository
from src.ticket.events import (
  ParallelWorkItemRequest,
  ParallelWorkItemsRequestedPayload,
  PrimaryOfficerAssignedPayload,
  TicketCategory,
  TicketDispatchedPayload,
  TicketEventType,
  TicketStatus,
  TicketWorkflowAction,
  TicketWorkflowState,
  TicketWorkItemKind,
  TicketWorkItemStatus,
  WorkItemCancelledPayload,
  WorkItemCompletedPayload,
)
from src.ticket.models import Ticket, TicketEvent, TicketSortField, TicketWorkItem
from src.ticket.repository import TicketRepository
from src.ticket.schemas import (
  ApproveEscalationAction,
  CancelWorkItemAction,
  CompleteWorkItemAction,
  EscalateTicketAction,
  ForwardTicketAction,
  PrimaryOfficerAssignmentRequest,
  RejectEscalationAction,
  RejectTicketAction,
  RequestCitizenResponseAction,
  RequestParallelCosignaturesAction,
  ResolveTicketAction,
  TicketAllowedActionsResponse,
  TicketCitizenResponseRequest,
  TicketDispatchRequest,
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketInternalResponse,
  TicketResponse,
  TicketWorkflowRequest,
  TicketWorkItemResponse,
)
from src.ticket.service import TicketService
from src.ticket.workflow_command_service import TicketWorkflowCommandService
from src.ticket.workflow_rules import (
  STAFF_ROLES,
  require_active_staff,
  require_current_coordinator,
  require_no_blocking_tasks,
)
from src.user.models import Role, User




class TicketWorkflowService:
  """Coordinates staff authorization, workflow events and task projections."""

  @staticmethod
  def _ticket_internal_response(
    ticket: Ticket,
    *,
    current_status_event: TicketEvent | None,
    current_user: User,
  ) -> TicketInternalResponse:
    """Builds the staff response while reusing the citizen DTO fields."""

    public_response = TicketService._ticket_response(
      ticket,
      current_status_event=current_status_event,
      current_user=current_user,
    )
    # Every officer or manager who passed the internal visibility check may add
    # revisioned evidence while the administrative workflow is still active.
    public_response.can_manage_images = (
      current_user.role in {Role.OFFICER, Role.MANAGER}
      and ticket.workflow_state != TicketWorkflowState.COMPLETED
    )
    return TicketInternalResponse(
      **public_response.model_dump(),
      workflow_state=ticket.workflow_state,
      primary_officer_id=ticket.primary_officer_id,
      current_responsible_user_id=ticket.current_responsible_user_id,
      pending_return_to_user_id=ticket.pending_return_to_user_id,
    )

  @staticmethod
  def _event_response(event: TicketEvent) -> TicketEventResponse:
    """Converts one persisted event into the internal API representation."""

    return TicketEventResponse(
      id=event.id,
      ticket_id=event.ticket_id,
      sequence_number=event.sequence_number,
      event_type=event.event_type,
      actor_user_id=event.actor_user_id,
      occurred_at=event.occurred_at,
      payload=event.payload,
      citizen_visible=event.citizen_visible,
      public_status=event.public_status,
      public_message=event.public_message,
    )

  @staticmethod
  def _work_item_response(work_item: TicketWorkItem) -> TicketWorkItemResponse:
    """Converts a projected parallel task into its API representation."""

    return TicketWorkItemResponse(
      id=work_item.id,
      ticket_id=work_item.ticket_id,
      group_id=work_item.group_id,
      kind=work_item.kind,
      status=work_item.status,
      outcome=work_item.outcome,
      assignee_user_id=work_item.assignee_user_id,
      requested_by_user_id=work_item.requested_by_user_id,
      return_to_user_id=work_item.return_to_user_id,
      is_blocking=work_item.is_blocking,
      comment=work_item.comment,
      created_at=work_item.created_at,
      completed_at=work_item.completed_at,
    )

  @staticmethod
  async def can_view_internal_ticket(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> bool:
    """Checks access to internal workflow data without granting admin access."""

    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role not in STAFF_ROLES:
      return False
    if current_user.id in {
      ticket.primary_officer_id,
      ticket.current_responsible_user_id,
      ticket.pending_return_to_user_id,
    }:
      return True
    if current_user.office_id is not None and current_user.office_id == ticket.office_id:
      return True
    return await TicketRepository.has_open_work_item_for_user(
      db,
      ticket.id,
      current_user.id,
    )

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
    internal = TicketWorkflowService._ticket_internal_response(
      ticket,
      current_status_event=latest.get(ticket.id),
      current_user=current_user,
    )
    work_items = await TicketRepository.get_work_items(db, ticket.id)
    allowed = await TicketWorkflowService._allowed_actions(db, ticket, current_user)
    return TicketInternalDetailResponse(
      **internal.model_dump(),
      work_items=[
        TicketWorkflowService._work_item_response(item) for item in work_items
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
      TicketWorkflowService._ticket_internal_response(
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
    if ticket is None or not await TicketWorkflowService.can_view_internal_ticket(
      db,
      ticket,
      current_user,
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowService._internal_detail_response(
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
    if ticket is None or not await TicketWorkflowService.can_view_internal_ticket(
      db,
      ticket,
      current_user,
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events = await TicketRepository.get_events(db, ticket.id)
    return [TicketWorkflowService._event_response(event) for event in events]

  @staticmethod
  async def get_allowed_actions(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketAllowedActionsResponse:
    """Returns commands the staff client may currently offer to the user."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketWorkflowService.can_view_internal_ticket(
      db,
      ticket,
      current_user,
    ):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowService._allowed_actions(db, ticket, current_user)

  @staticmethod
  async def dispatch_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketDispatchRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Assigns a central-inbox ticket to an active office."""

    if current_user.role != Role.DISPATCHER:
      raise ForbiddenException("Only dispatchers may route tickets")

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    if ticket.primary_officer_id is not None or ticket.workflow_state not in {
      TicketWorkflowState.NEW,
      TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    }:
      raise WorkflowValidationException(
        "Only tickets without a primary officer may be dispatched."
      )

    office = await OfficeRepository.get_by_id(db, request.office_id)
    if office is None or not office.is_active:
      raise WorkflowValidationException("The selected office is not active.")

    await TicketService._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_DISPATCHED,
      payload=TicketDispatchedPayload(
        office_id=office.id,
        comment=request.comment,
      ),
    )
    return await TicketWorkflowService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def assign_primary_officer(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: PrimaryOfficerAssignmentRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Lets the responsible office manager select the permanent case owner."""

    if current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may assign a primary officer")

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    if (
      ticket.workflow_state != TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
      or ticket.office_id is None
      or ticket.primary_officer_id is not None
    ):
      raise WorkflowValidationException(
        "The ticket is not waiting for its initial primary officer."
      )
    if current_user.office_id != ticket.office_id:
      raise ForbiddenException("Only a manager of the assigned office may act")

    officer = await require_active_staff(
      db,
      request.primary_officer_id,
      roles={Role.OFFICER},
      error_message=(
        "The primary officer must be an active officer of the assigned office."
      ),
    )
    if officer.office_id != ticket.office_id:
      raise WorkflowValidationException(
        "The primary officer must be an active officer of the assigned office."
      )

    await TicketService._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.PRIMARY_OFFICER_ASSIGNED,
      payload=PrimaryOfficerAssignedPayload(
        primary_officer_id=officer.id,
        comment=request.comment,
      ),
    )
    return await TicketWorkflowService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def execute_workflow(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketWorkflowRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Dispatches one validated polymorphic workflow command."""

    if isinstance(request, RequestParallelCosignaturesAction):
      return await TicketWorkflowService._request_parallel_cosignatures(
        db, ticket_id, request, current_user
      )
    if isinstance(request, CompleteWorkItemAction):
      return await TicketWorkflowService._complete_work_item(
        db, ticket_id, request, current_user
      )
    if isinstance(request, CancelWorkItemAction):
      return await TicketWorkflowService._cancel_work_item(
        db, ticket_id, request, current_user
      )

    command_handlers = {
      ForwardTicketAction: TicketWorkflowCommandService.forward_ticket,
      EscalateTicketAction: TicketWorkflowCommandService.escalate_ticket,
      ApproveEscalationAction: TicketWorkflowCommandService.approve_escalation,
      RejectEscalationAction: TicketWorkflowCommandService.reject_escalation,
      RequestCitizenResponseAction: TicketWorkflowCommandService.request_citizen_response,
      ResolveTicketAction: TicketWorkflowCommandService.resolve_ticket,
      RejectTicketAction: TicketWorkflowCommandService.reject_ticket,
    }
    for request_type, handler in command_handlers.items():
      if isinstance(request, request_type):
        ticket = await handler(db, ticket_id, request, current_user)
        return await TicketWorkflowService._internal_detail_response(
          db, ticket, current_user
        )
    raise WorkflowValidationException("Unsupported workflow action.")

  @staticmethod
  async def _request_parallel_cosignatures(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: RequestParallelCosignaturesAction,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Creates one non-nested parallel cosignature round."""

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
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
    event = await TicketService._append_event(
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
    return await TicketWorkflowService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def _complete_work_item(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CompleteWorkItemAction,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Completes one task while sibling tasks remain independently open."""

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    work_item = await TicketRepository.get_work_item_for_update(db, request.work_item_id)
    if work_item is None or work_item.ticket_id != ticket.id:
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
    event = await TicketService._append_event(
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
    return await TicketWorkflowService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def _cancel_work_item(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: CancelWorkItemAction,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Cancels one open task without modifying completed sibling tasks."""

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    require_current_coordinator(ticket, current_user)

    work_item = await TicketRepository.get_work_item_for_update(db, request.work_item_id)
    if work_item is None or work_item.ticket_id != ticket.id:
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
    event = await TicketService._append_event(
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
    return await TicketWorkflowService._internal_detail_response(
      db,
      ticket,
      current_user,
    )


  @staticmethod
  async def respond_as_citizen(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketCitizenResponseRequest,
    current_user: User,
  ) -> TicketResponse:
    """Returns the citizen-facing projection after a requested response."""

    ticket, event = await TicketWorkflowCommandService.respond_as_citizen(
      db, ticket_id, request, current_user
    )
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketService._ticket_response(
      ticket,
      current_status_event=latest.get(ticket.id) or event,
      current_user=current_user,
    )
