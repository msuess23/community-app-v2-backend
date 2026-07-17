"""Dispatches polymorphic workflow request models to focused command services."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import WorkflowValidationException
from src.ticket.schemas import (
  ApproveEscalationAction, CancelWorkItemAction, CompleteWorkItemAction,
  EscalateTicketAction, ForwardTicketAction, RejectEscalationAction, RejectTicketAction, RequestCitizenResponseAction,
  RequestParallelCosignaturesAction, ResolveTicketAction, TicketInternalDetailResponse, TicketWorkflowRequest,
)
from src.ticket.services.workflow.commands import TicketWorkflowCommandService
from src.ticket.services.workflow.queries import TicketWorkflowQueryService
from src.user.models import User

from src.ticket.services.workflow.work_items import TicketWorkItemService


class TicketWorkflowDispatcher:
  """Routes one validated workflow command to its application service."""

  @staticmethod
  async def execute_workflow(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketWorkflowRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Dispatches one validated polymorphic workflow command."""

    if isinstance(request, RequestParallelCosignaturesAction):
      return await TicketWorkItemService.request_parallel_cosignatures(
        db, ticket_id, request, current_user
      )
    if isinstance(request, CompleteWorkItemAction):
      return await TicketWorkItemService.complete_work_item(
        db, ticket_id, request, current_user
      )
    if isinstance(request, CancelWorkItemAction):
      return await TicketWorkItemService.cancel_work_item(
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
        return await TicketWorkflowQueryService._internal_detail_response(
          db, ticket, current_user
        )
    raise WorkflowValidationException("Unsupported workflow action.")
