from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.ticket.domain import (
  CosignatureRequestedPayload,
  EscalationDecision,
  EscalationDecisionPayload,
  PrimaryOfficerAssignedPayload,
  TicketCategory,
  TicketCompletedPayload,
  TicketCompletionOutcome,
  TicketCosignedPayload,
  TicketDispatchedPayload,
  TicketEventType,
  TicketStatus,
  TicketSubmittedPayload,
  TicketWorkflowState,
  evolve_ticket,
  rebuild_ticket,
)


def _active_state(now: datetime):
  primary = uuid4()
  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Pothole",
      category=TicketCategory.INFRASTRUCTURE,
      creator_user_id=uuid4(),
    ),
    occurred_at=now,
  )
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_DISPATCHED,
    TicketDispatchedPayload(office_id=uuid4()),
    occurred_at=now + timedelta(minutes=1),
  )
  state = evolve_ticket(
    state,
    TicketEventType.PRIMARY_OFFICER_ASSIGNED,
    PrimaryOfficerAssignedPayload(primary_officer_id=primary),
    occurred_at=now + timedelta(minutes=2),
  )
  return state, primary


def test_submission_starts_in_central_inbox() -> None:
  now = datetime.now(timezone.utc)
  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Broken street light",
      category=TicketCategory.SAFETY,
      creator_user_id=uuid4(),
    ),
    occurred_at=now,
  )
  assert state.office_id is None
  assert state.workflow_state == TicketWorkflowState.NEW
  assert state.public_status == TicketStatus.OPEN
  assert state.version == 1


def test_sequential_cosignature_returns_to_requester() -> None:
  now = datetime.now(timezone.utc)
  state, requester = _active_state(now)
  cosigner = uuid4()

  state = evolve_ticket(
    state,
    TicketEventType.COSIGNATURE_REQUESTED,
    CosignatureRequestedPayload(
      target_user_id=cosigner,
      return_to_user_id=requester,
      comment="Please cosign",
    ),
    occurred_at=now + timedelta(minutes=3),
  )
  assert state.workflow_state == TicketWorkflowState.WAITING_FOR_COSIGNATURE
  assert state.current_assignee_id == cosigner
  assert state.return_to_user_id == requester

  state = evolve_ticket(
    state,
    TicketEventType.TICKET_COSIGNED,
    TicketCosignedPayload(return_to_user_id=requester, comment="Approved"),
    occurred_at=now + timedelta(minutes=4),
  )
  assert state.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert state.current_assignee_id == requester
  assert state.return_to_user_id is None


def test_escalation_decision_uses_one_event_type() -> None:
  now = datetime.now(timezone.utc)
  state, requester = _active_state(now)
  manager = uuid4()
  from src.ticket.domain import TicketEscalatedPayload

  state = evolve_ticket(
    state,
    TicketEventType.TICKET_ESCALATED,
    TicketEscalatedPayload(
      manager_user_id=manager,
      return_to_user_id=requester,
      reason="Approval required",
    ),
    occurred_at=now + timedelta(minutes=3),
  )
  assert state.workflow_state == TicketWorkflowState.WAITING_FOR_DECISION

  state = evolve_ticket(
    state,
    TicketEventType.ESCALATION_DECIDED,
    EscalationDecisionPayload(
      return_to_user_id=requester,
      decision=EscalationDecision.APPROVED,
      comment="Approved",
    ),
    occurred_at=now + timedelta(minutes=4),
  )
  assert state.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert state.current_assignee_id == requester


def test_completion_uses_outcome_payload_and_completed_at() -> None:
  now = datetime.now(timezone.utc)
  state, _ = _active_state(now)
  completed_at = now + timedelta(minutes=3)
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_COMPLETED,
    TicketCompletedPayload(
      outcome=TicketCompletionOutcome.RESOLVED,
      message="Road repaired",
    ),
    occurred_at=completed_at,
  )
  assert state.public_status == TicketStatus.RESOLVED
  assert state.workflow_state == TicketWorkflowState.COMPLETED
  assert state.completed_at == completed_at


def test_rebuild_ticket_replays_simplified_event_stream() -> None:
  now = datetime.now(timezone.utc)
  creator = uuid4()
  events = [
    (
      TicketEventType.TICKET_SUBMITTED,
      TicketSubmittedPayload(
        title="Noise",
        category=TicketCategory.NOISE,
        creator_user_id=creator,
      ).model_dump(mode="json"),
      now,
    ),
    (
      TicketEventType.TICKET_CANCELLED,
      {"reason": "Duplicate"},
      now + timedelta(minutes=1),
    ),
  ]
  state = rebuild_ticket(events)
  assert state.creator_user_id == creator
  assert state.public_status == TicketStatus.CANCELLED
  assert state.version == 2


def test_primary_officer_reassignment_updates_matching_return_targets() -> None:
  from src.ticket.domain import PrimaryOfficerReassignedPayload

  now = datetime.now(timezone.utc)
  state, previous = _active_state(now)
  temporary_assignee = uuid4()
  replacement = uuid4()
  state.current_assignee_id = temporary_assignee
  state.return_to_user_id = previous

  state = evolve_ticket(
    state,
    TicketEventType.PRIMARY_OFFICER_REASSIGNED,
    PrimaryOfficerReassignedPayload(
      previous_primary_officer_id=previous,
      new_primary_officer_id=replacement,
      comment="Long-term substitution",
    ),
    occurred_at=now + timedelta(minutes=3),
  )

  assert state.primary_officer_id == replacement
  assert state.current_assignee_id == temporary_assignee
  assert state.return_to_user_id == replacement


def test_return_to_dispatch_clears_office_ownership_for_redispatch() -> None:
  from src.ticket.domain import TicketReturnedToDispatchPayload

  now = datetime.now(timezone.utc)
  state, primary = _active_state(now)
  previous_office = state.office_id
  assert previous_office is not None

  state = evolve_ticket(
    state,
    TicketEventType.TICKET_RETURNED_TO_DISPATCH,
    TicketReturnedToDispatchPayload(
      previous_office_id=previous_office,
      previous_primary_officer_id=primary,
      reason="Wrong authority",
    ),
    occurred_at=now + timedelta(minutes=3),
  )

  assert state.office_id is None
  assert state.primary_officer_id is None
  assert state.current_assignee_id is None
  assert state.return_to_user_id is None
  assert state.workflow_state == TicketWorkflowState.NEW
  assert state.public_status == TicketStatus.IN_PROGRESS
