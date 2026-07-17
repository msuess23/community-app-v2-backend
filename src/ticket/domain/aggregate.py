"""Pure state evolution and replay for the ticket aggregate."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.ticket.domain.enums import (
  TicketCategory, TicketEventType, TicketStatus, TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.domain.payloads import (
  AddressSnapshot, CitizenRespondedPayload, CitizenResponseRequestedPayload,
  EscalationDecisionPayload, PrimaryOfficerAssignedPayload,
  TicketCompletedPayload, TicketDetailsUpdatedPayload,
  TicketDispatchedPayload, TicketEscalatedPayload, TicketForwardedPayload,
  TicketSubmittedPayload, validate_event_payload,
)

class TicketAggregateState(BaseModel):
  """Pure aggregate state rebuilt from the ordered ticket event stream."""

  model_config = ConfigDict(validate_assignment=True)

  title: str
  description: str | None = None
  category: TicketCategory
  creator_user_id: UUID
  office_id: UUID | None = None
  address: AddressSnapshot | None = None
  visibility: TicketVisibility
  public_status: TicketStatus
  public_status_message: str | None = None
  workflow_state: TicketWorkflowState
  primary_officer_id: UUID | None = None
  current_responsible_user_id: UUID | None = None
  pending_return_to_user_id: UUID | None = None
  version: int = 0
  created_at: datetime
  updated_at: datetime
  resolved_at: datetime | None = None
  cancelled_at: datetime | None = None

def evolve_ticket(
  state: TicketAggregateState | None,
  event_type: TicketEventType,
  payload: BaseModel | dict[str, Any],
  *,
  occurred_at: datetime,
) -> TicketAggregateState:
  """Applies one validated event and returns the resulting ticket state.

  The function implements only deterministic state changes.  Authorization and
  workflow preconditions remain in the service layer because they depend on the
  current actor and database-backed assignments.
  """

  validated = validate_event_payload(event_type, payload)

  if event_type == TicketEventType.TICKET_SUBMITTED:
    if state is not None:
      raise ValueError("TICKET_SUBMITTED must be the first aggregate event")
    submitted = validated
    assert isinstance(submitted, TicketSubmittedPayload)
    return TicketAggregateState(
      title=submitted.title,
      description=submitted.description,
      category=submitted.category,
      creator_user_id=submitted.creator_user_id,
      address=submitted.address,
      visibility=submitted.visibility,
      public_status=TicketStatus.OPEN,
      public_status_message="Ticket submitted",
      workflow_state=TicketWorkflowState.NEW,
      version=1,
      created_at=occurred_at,
      updated_at=occurred_at,
    )

  if state is None:
    raise ValueError(f"{event_type.value} requires an existing ticket state")

  next_state = state.model_copy(deep=True)
  next_state.version += 1
  next_state.updated_at = occurred_at

  if event_type == TicketEventType.TICKET_DETAILS_UPDATED:
    updated = validated
    assert isinstance(updated, TicketDetailsUpdatedPayload)
    # model_fields_set preserves an explicit null used to clear optional fields.
    for field_name in updated.model_fields_set:
      setattr(next_state, field_name, getattr(updated, field_name))
  elif event_type == TicketEventType.TICKET_CANCELLED:
    next_state.public_status = TicketStatus.CANCELLED
    next_state.public_status_message = "Ticket cancelled"
    next_state.workflow_state = TicketWorkflowState.COMPLETED
    next_state.current_responsible_user_id = None
    next_state.pending_return_to_user_id = None
    next_state.cancelled_at = occurred_at
  elif event_type == TicketEventType.TICKET_DISPATCHED:
    dispatched = validated
    assert isinstance(dispatched, TicketDispatchedPayload)
    next_state.office_id = dispatched.office_id
    next_state.public_status = TicketStatus.IN_PROGRESS
    next_state.public_status_message = "Forwarded to the responsible office"
    next_state.workflow_state = TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
  elif event_type == TicketEventType.PRIMARY_OFFICER_ASSIGNED:
    assigned = validated
    assert isinstance(assigned, PrimaryOfficerAssignedPayload)
    next_state.primary_officer_id = assigned.primary_officer_id
    next_state.current_responsible_user_id = assigned.primary_officer_id
    next_state.workflow_state = TicketWorkflowState.IN_PROGRESS
  elif event_type == TicketEventType.TICKET_FORWARDED:
    forwarded = validated
    assert isinstance(forwarded, TicketForwardedPayload)
    next_state.current_responsible_user_id = forwarded.target_user_id
    next_state.pending_return_to_user_id = None
  elif event_type == TicketEventType.CITIZEN_RESPONSE_REQUESTED:
    request = validated
    assert isinstance(request, CitizenResponseRequestedPayload)
    next_state.workflow_state = TicketWorkflowState.WAITING_FOR_CITIZEN
    next_state.current_responsible_user_id = state.creator_user_id
    next_state.pending_return_to_user_id = request.return_to_user_id
    next_state.public_status_message = request.question
  elif event_type == TicketEventType.CITIZEN_RESPONDED:
    response = validated
    assert isinstance(response, CitizenRespondedPayload)
    next_state.workflow_state = TicketWorkflowState.IN_PROGRESS
    next_state.current_responsible_user_id = response.return_to_user_id
    next_state.pending_return_to_user_id = None
    next_state.public_status_message = "Citizen response received"
  elif event_type == TicketEventType.TICKET_ESCALATED:
    escalation = validated
    assert isinstance(escalation, TicketEscalatedPayload)
    next_state.workflow_state = TicketWorkflowState.WAITING_FOR_APPROVAL
    next_state.current_responsible_user_id = escalation.manager_user_id
    next_state.pending_return_to_user_id = escalation.return_to_user_id
  elif event_type in {
    TicketEventType.ESCALATION_APPROVED,
    TicketEventType.ESCALATION_REJECTED,
  }:
    decision = validated
    assert isinstance(decision, EscalationDecisionPayload)
    next_state.workflow_state = TicketWorkflowState.IN_PROGRESS
    next_state.current_responsible_user_id = decision.return_to_user_id
    next_state.pending_return_to_user_id = None
    if event_type == TicketEventType.ESCALATION_APPROVED:
      next_state.public_status_message = decision.comment or "Proposed measure approved"
  elif event_type == TicketEventType.TICKET_RESOLVED:
    completed = validated
    assert isinstance(completed, TicketCompletedPayload)
    next_state.public_status = TicketStatus.RESOLVED
    next_state.public_status_message = completed.message or "Ticket resolved"
    next_state.workflow_state = TicketWorkflowState.COMPLETED
    next_state.current_responsible_user_id = None
    next_state.pending_return_to_user_id = None
    next_state.resolved_at = occurred_at
  elif event_type == TicketEventType.TICKET_REJECTED:
    completed = validated
    assert isinstance(completed, TicketCompletedPayload)
    next_state.public_status = TicketStatus.REJECTED
    next_state.public_status_message = completed.message or "Ticket rejected"
    next_state.workflow_state = TicketWorkflowState.COMPLETED
    next_state.current_responsible_user_id = None
    next_state.pending_return_to_user_id = None
    next_state.resolved_at = occurred_at
  # Work-item, comment and image events update their own read models.  They
  # still advance the aggregate version so the complete stream stays ordered.

  return next_state


def rebuild_ticket(
  events: list[tuple[TicketEventType, dict[str, Any], datetime]],
) -> TicketAggregateState:
  """Rebuilds an aggregate from an already ordered list of persisted events."""

  state: TicketAggregateState | None = None
  for event_type, payload, occurred_at in events:
    state = evolve_ticket(
      state,
      event_type,
      payload,
      occurred_at=occurred_at,
    )
  if state is None:
    raise ValueError("A ticket aggregate requires at least one event")
  return state
