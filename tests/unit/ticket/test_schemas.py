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
  TicketInternalResponse,
  TicketResponse,
  TicketStatusResponse,
)


def test_ticket_response_uses_plain_snake_case_fields() -> None:
  now = datetime.now(timezone.utc)
  response = TicketResponse(
    id=uuid4(),
    title="Pothole",
    category=TicketCategory.INFRASTRUCTURE,
    visibility=TicketVisibility.PUBLIC,
    created_at=now,
    current_status=TicketStatusResponse(
      id=uuid4(),
      status=TicketStatus.OPEN,
      created_at=now,
    ),
    version=1,
  )

  data = response.model_dump()
  assert "creator_user_id" not in data
  assert "current_status" in data

  internal = TicketInternalResponse(
    **data,
    creator_user_id=uuid4(),
    workflow_state="NEW",
  )
  assert "creator_user_id" in internal.model_dump()


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


def test_ticket_update_rejects_null_for_non_clearable_fields() -> None:
  from src.ticket.schemas import TicketUpdateRequest

  for payload in (
    {"title": None},
    {"category": None},
    {"visibility": None},
  ):
    with pytest.raises(ValidationError):
      TicketUpdateRequest.model_validate(payload)

  update = TicketUpdateRequest(description=None, address=None)
  assert update.description is None
  assert update.address is None


def test_workflow_requests_reject_unknown_fields() -> None:
  with pytest.raises(ValidationError):
    RequestCosignatureAction.model_validate(
      {
        "action": TicketWorkflowAction.REQUEST_COSIGNATURE,
        "target_user_id": uuid4(),
        "unexpected": True,
      }
    )
