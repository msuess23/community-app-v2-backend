"""Domain events and pure projection logic for the ticket aggregate.

The database event table stores the validated payload of these events.  The
functions in this module deliberately avoid SQLAlchemy so the aggregate can be
rebuilt and tested without a database connection.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Any, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class TicketCategory(str, enum.Enum):
  """Categories retained from the previous Ktor ticket API."""

  INFRASTRUCTURE = "INFRASTRUCTURE"
  CLEANING = "CLEANING"
  SAFETY = "SAFETY"
  NOISE = "NOISE"
  OTHER = "OTHER"


class TicketVisibility(str, enum.Enum):
  """Controls whether a ticket is visible in the public community list."""

  PUBLIC = "PUBLIC"
  PRIVATE = "PRIVATE"


class TicketStatus(str, enum.Enum):
  """Coarse processing status that may be exposed to citizens."""

  OPEN = "OPEN"
  IN_PROGRESS = "IN_PROGRESS"
  RESOLVED = "RESOLVED"
  REJECTED = "REJECTED"
  CANCELLED = "CANCELLED"


class TicketWorkflowState(str, enum.Enum):
  """Internal workflow state used by the administrative client."""

  NEW = "NEW"
  AWAITING_PRIMARY_ASSIGNMENT = "AWAITING_PRIMARY_ASSIGNMENT"
  IN_PROGRESS = "IN_PROGRESS"
  WAITING_FOR_CITIZEN = "WAITING_FOR_CITIZEN"
  WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
  COMPLETED = "COMPLETED"


class TicketEventType(str, enum.Enum):
  """All event types anticipated by the first workflow iteration."""

  TICKET_SUBMITTED = "TICKET_SUBMITTED"
  TICKET_DETAILS_UPDATED = "TICKET_DETAILS_UPDATED"
  TICKET_CANCELLED = "TICKET_CANCELLED"
  TICKET_DISPATCHED = "TICKET_DISPATCHED"
  PRIMARY_OFFICER_ASSIGNED = "PRIMARY_OFFICER_ASSIGNED"
  TICKET_FORWARDED = "TICKET_FORWARDED"
  PARALLEL_WORK_ITEMS_REQUESTED = "PARALLEL_WORK_ITEMS_REQUESTED"
  WORK_ITEM_COMPLETED = "WORK_ITEM_COMPLETED"
  WORK_ITEM_CANCELLED = "WORK_ITEM_CANCELLED"
  CITIZEN_RESPONSE_REQUESTED = "CITIZEN_RESPONSE_REQUESTED"
  CITIZEN_RESPONDED = "CITIZEN_RESPONDED"
  TICKET_ESCALATED = "TICKET_ESCALATED"
  ESCALATION_APPROVED = "ESCALATION_APPROVED"
  ESCALATION_REJECTED = "ESCALATION_REJECTED"
  TICKET_RESOLVED = "TICKET_RESOLVED"
  TICKET_REJECTED = "TICKET_REJECTED"
  TICKET_COMMENTED = "TICKET_COMMENTED"
  TICKET_IMAGE_ADDED = "TICKET_IMAGE_ADDED"
  TICKET_IMAGE_REMOVED = "TICKET_IMAGE_REMOVED"
  TICKET_COVER_IMAGE_CHANGED = "TICKET_COVER_IMAGE_CHANGED"


class TicketWorkItemKind(str, enum.Enum):
  """A small set of parallel subtasks supported by the workflow."""

  COSIGNATURE = "COSIGNATURE"
  CONSULTATION = "CONSULTATION"
  APPROVAL = "APPROVAL"


class TicketWorkItemStatus(str, enum.Enum):
  """Lifecycle of a projected workflow work item."""

  OPEN = "OPEN"
  COMPLETED = "COMPLETED"
  CANCELLED = "CANCELLED"


class TicketWorkItemOutcome(str, enum.Enum):
  """Possible results of a completed review task."""

  APPROVED = "APPROVED"
  REJECTED = "REJECTED"
  ACKNOWLEDGED = "ACKNOWLEDGED"


class TicketWorkflowAction(str, enum.Enum):
  """Workflow commands currently exposed by the administrative API."""

  DISPATCH = "DISPATCH"
  ASSIGN_PRIMARY_OFFICER = "ASSIGN_PRIMARY_OFFICER"
  REQUEST_PARALLEL_COSIGNATURES = "REQUEST_PARALLEL_COSIGNATURES"
  COMPLETE_WORK_ITEM = "COMPLETE_WORK_ITEM"
  CANCEL_WORK_ITEM = "CANCEL_WORK_ITEM"
  FORWARD = "FORWARD"
  ESCALATE = "ESCALATE"
  APPROVE_ESCALATION = "APPROVE_ESCALATION"
  REJECT_ESCALATION = "REJECT_ESCALATION"
  REQUEST_CITIZEN_RESPONSE = "REQUEST_CITIZEN_RESPONSE"
  RESOLVE = "RESOLVE"
  REJECT_TICKET = "REJECT_TICKET"


class AddressSnapshot(BaseModel):
  """Immutable address value embedded in ticket event payloads."""

  street: str
  house_number: str
  zip_code: str
  city: str
  latitude: float | None = None
  longitude: float | None = None


class TicketSubmittedPayload(BaseModel):
  """Complete initial state required to rebuild a submitted ticket."""

  title: str
  description: str | None = None
  category: TicketCategory
  creator_user_id: UUID
  address: AddressSnapshot | None = None
  visibility: TicketVisibility = TicketVisibility.PUBLIC


class TicketDetailsUpdatedPayload(BaseModel):
  """Only the explicitly changed citizen-editable ticket fields."""

  title: str | None = None
  description: str | None = None
  category: TicketCategory | None = None
  address: AddressSnapshot | None = None
  visibility: TicketVisibility | None = None


class TicketCancelledPayload(BaseModel):
  """Optional explanation supplied when a citizen cancels a new ticket."""

  reason: str | None = None


class TicketDispatchedPayload(BaseModel):
  """Assigns an unclassified ticket to the responsible office."""

  office_id: UUID
  comment: str | None = None


class PrimaryOfficerAssignedPayload(BaseModel):
  """Stores the permanent case owner selected by the office manager."""

  primary_officer_id: UUID
  comment: str | None = None


class TicketForwardedPayload(BaseModel):
  """Moves overall coordination to another employee without changing ownership."""

  target_user_id: UUID
  comment: str | None = None


class ParallelWorkItemRequest(BaseModel):
  """One task in a small parallel review group."""

  assignee_user_id: UUID
  kind: TicketWorkItemKind
  comment: str | None = None
  is_blocking: bool = True


class ParallelWorkItemsRequestedPayload(BaseModel):
  """Creates one or more tasks that may be processed concurrently."""

  group_id: UUID
  return_to_user_id: UUID
  items: Annotated[list[ParallelWorkItemRequest], Field(min_length=1, max_length=10)]

  @field_validator("items")
  @classmethod
  def prevent_duplicate_assignees(
    cls,
    items: list[ParallelWorkItemRequest],
  ) -> list[ParallelWorkItemRequest]:
    assignees = [item.assignee_user_id for item in items]
    if len(assignees) != len(set(assignees)):
      raise ValueError("parallel work items must use distinct assignees")
    return items


class WorkItemCompletedPayload(BaseModel):
  """Completes a single projected task without closing sibling tasks."""

  work_item_id: UUID
  outcome: TicketWorkItemOutcome
  comment: str | None = None


class WorkItemCancelledPayload(BaseModel):
  """Cancels one no-longer-required projected workflow task."""

  work_item_id: UUID
  reason: str | None = None


class CitizenResponseRequestedPayload(BaseModel):
  """Requests additional information from the ticket creator."""

  question: str
  return_to_user_id: UUID


class CitizenRespondedPayload(BaseModel):
  """Stores the citizen response and returns coordination to an employee."""

  message: str
  return_to_user_id: UUID


class TicketEscalatedPayload(BaseModel):
  """Temporarily moves case coordination to a manager for a decision."""

  manager_user_id: UUID
  return_to_user_id: UUID
  reason: str


class EscalationDecisionPayload(BaseModel):
  """Records an approval decision and the employee receiving the case back."""

  return_to_user_id: UUID
  comment: str | None = None


class TicketCompletedPayload(BaseModel):
  """Explanation exposed with a final resolved or rejected status."""

  message: str | None = None


class TicketCommentedPayload(BaseModel):
  """Append-only public comment or internal case-note payload."""

  text: str
  is_internal: bool = True


class TicketImageAddedPayload(BaseModel):
  """Immutable metadata for one file added to a ticket."""

  image_id: UUID
  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int
  is_cover: bool


class TicketImageRemovedPayload(BaseModel):
  """Marks a projected image as removed without deleting its stored file."""

  image_id: UUID
  reason: str | None = None


class TicketCoverImageChangedPayload(BaseModel):
  """Selects the image represented by the legacy imageUrl response field."""

  image_id: UUID


EventPayload: TypeAlias = (
  TicketSubmittedPayload
  | TicketDetailsUpdatedPayload
  | TicketCancelledPayload
  | TicketDispatchedPayload
  | PrimaryOfficerAssignedPayload
  | TicketForwardedPayload
  | ParallelWorkItemsRequestedPayload
  | WorkItemCompletedPayload
  | WorkItemCancelledPayload
  | CitizenResponseRequestedPayload
  | CitizenRespondedPayload
  | TicketEscalatedPayload
  | EscalationDecisionPayload
  | TicketCompletedPayload
  | TicketCommentedPayload
  | TicketImageAddedPayload
  | TicketImageRemovedPayload
  | TicketCoverImageChangedPayload
)


_EVENT_PAYLOAD_TYPES: dict[TicketEventType, type[BaseModel]] = {
  TicketEventType.TICKET_SUBMITTED: TicketSubmittedPayload,
  TicketEventType.TICKET_DETAILS_UPDATED: TicketDetailsUpdatedPayload,
  TicketEventType.TICKET_CANCELLED: TicketCancelledPayload,
  TicketEventType.TICKET_DISPATCHED: TicketDispatchedPayload,
  TicketEventType.PRIMARY_OFFICER_ASSIGNED: PrimaryOfficerAssignedPayload,
  TicketEventType.TICKET_FORWARDED: TicketForwardedPayload,
  TicketEventType.PARALLEL_WORK_ITEMS_REQUESTED: ParallelWorkItemsRequestedPayload,
  TicketEventType.WORK_ITEM_COMPLETED: WorkItemCompletedPayload,
  TicketEventType.WORK_ITEM_CANCELLED: WorkItemCancelledPayload,
  TicketEventType.CITIZEN_RESPONSE_REQUESTED: CitizenResponseRequestedPayload,
  TicketEventType.CITIZEN_RESPONDED: CitizenRespondedPayload,
  TicketEventType.TICKET_ESCALATED: TicketEscalatedPayload,
  TicketEventType.ESCALATION_APPROVED: EscalationDecisionPayload,
  TicketEventType.ESCALATION_REJECTED: EscalationDecisionPayload,
  TicketEventType.TICKET_RESOLVED: TicketCompletedPayload,
  TicketEventType.TICKET_REJECTED: TicketCompletedPayload,
  TicketEventType.TICKET_COMMENTED: TicketCommentedPayload,
  TicketEventType.TICKET_IMAGE_ADDED: TicketImageAddedPayload,
  TicketEventType.TICKET_IMAGE_REMOVED: TicketImageRemovedPayload,
  TicketEventType.TICKET_COVER_IMAGE_CHANGED: TicketCoverImageChangedPayload,
}


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


def validate_event_payload(
  event_type: TicketEventType,
  payload: BaseModel | dict[str, Any],
) -> EventPayload:
  """Validates a payload against the schema assigned to its event type."""

  payload_type = _EVENT_PAYLOAD_TYPES[event_type]
  return TypeAdapter(payload_type).validate_python(payload)


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
