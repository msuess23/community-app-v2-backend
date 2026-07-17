from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ticket.domain import (
  EscalationDecision,
  TicketCategory,
  TicketCompletionOutcome,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowAction,
)
from src.ticket.schemas import (
  CompleteTicketAction,
  DecideEscalationAction,
  RequestCosignatureAction,
  TicketResponse,
  TicketStatusResponse,
)


def test_ticket_response_uses_plain_snake_case_fields() -> None:
  now = datetime.now(timezone.utc)
  response = TicketResponse(
    id=uuid4(),
    title="Pothole",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=uuid4(),
    visibility=TicketVisibility.PUBLIC,
    created_at=now,
    current_status=TicketStatusResponse(
      id=uuid4(),
      status=TicketStatus.OPEN,
      created_by_user_id=uuid4(),
      created_at=now,
    ),
    version=1,
  )

  data = response.model_dump()
  assert "creator_user_id" in data
  assert "current_status" in data
  assert "creatorUserId" not in data


def test_cosignature_action_rejects_camel_case_input() -> None:
  target = uuid4()
  action = RequestCosignatureAction(
    action=TicketWorkflowAction.REQUEST_COSIGNATURE,
    target_user_id=target,
    comment="Please review",
  )
  assert action.target_user_id == target

  with pytest.raises(ValidationError):
    RequestCosignatureAction(
      action=TicketWorkflowAction.REQUEST_COSIGNATURE,
      targetUserId=target,
    )


def test_combined_decision_and_completion_actions_validate() -> None:
  decision = DecideEscalationAction(
    action=TicketWorkflowAction.DECIDE_ESCALATION,
    decision=EscalationDecision.APPROVED,
  )
  completion = CompleteTicketAction(
    action=TicketWorkflowAction.COMPLETE,
    outcome=TicketCompletionOutcome.RESOLVED,
    message="Completed",
  )
  assert decision.decision == EscalationDecision.APPROVED
  assert completion.outcome == TicketCompletionOutcome.RESOLVED
