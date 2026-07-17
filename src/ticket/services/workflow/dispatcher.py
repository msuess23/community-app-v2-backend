"""Dispatch polymorphic workflow request models to command handlers."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import WorkflowValidationException
from src.ticket.schemas import (
  CompleteTicketAction,
  CosignTicketAction,
  DecideEscalationAction,
  EscalateTicketAction,
  ForwardTicketAction,
  RequestCitizenResponseAction,
  RequestCosignatureAction,
  TicketInternalDetailResponse,
  TicketWorkflowRequest,
)
from src.ticket.services.workflow.commands import TicketWorkflowCommandService
from src.ticket.services.workflow.queries import TicketWorkflowQueryService
from src.user.models import User


class TicketWorkflowDispatcher:
  """Route one validated workflow command to its application handler."""

  @staticmethod
  async def execute_workflow(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketWorkflowRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Execute one supported workflow command and return the new detail."""

    handlers = {
      ForwardTicketAction: TicketWorkflowCommandService.forward_ticket,
      RequestCosignatureAction: TicketWorkflowCommandService.request_cosignature,
      CosignTicketAction: TicketWorkflowCommandService.cosign_ticket,
      EscalateTicketAction: TicketWorkflowCommandService.escalate_ticket,
      DecideEscalationAction: TicketWorkflowCommandService.decide_escalation,
      RequestCitizenResponseAction: TicketWorkflowCommandService.request_citizen_response,
      CompleteTicketAction: TicketWorkflowCommandService.complete_ticket,
    }
    for request_type, handler in handlers.items():
      if isinstance(request, request_type):
        ticket = await handler(db, ticket_id, request, current_user)
        return await TicketWorkflowQueryService._internal_detail_response(
          db, ticket, current_user
        )
    raise WorkflowValidationException("Unsupported workflow action.")
