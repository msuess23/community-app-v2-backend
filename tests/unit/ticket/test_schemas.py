from datetime import datetime, timezone
from uuid import uuid4

from src.ticket.events import (
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


def test_ticket_response_keeps_existing_camel_case_contract_for_now() -> None:
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

  data = response.model_dump(by_alias=True)
  assert "creatorUserId" in data
  assert "currentStatus" in data
  assert "votesCount" not in data


def test_cosignature_action_uses_one_target_user() -> None:
  target = uuid4()
  action = RequestCosignatureAction(
    action=TicketWorkflowAction.REQUEST_COSIGNATURE,
    targetUserId=target,
    comment="Please review",
  )
  assert action.target_user_id == target


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
