"""Administrative workflow commands and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import Field, field_validator

from src.ticket.events import (
  TicketEventType, TicketStatus, TicketWorkflowAction, TicketWorkItemKind,
  TicketWorkItemOutcome, TicketWorkItemStatus,
)
from src.ticket.schemas.base import TicketApiModel, _normalize_optional_text, _normalize_required_text
from src.ticket.schemas.ticket import TicketInternalResponse

class TicketDispatchRequest(TicketApiModel):
  """Dispatcher command that selects the authority responsible for a ticket."""

  office_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class PrimaryOfficerAssignmentRequest(TicketApiModel):
  """Manager command that selects the permanent officer for a ticket."""

  primary_officer_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class RequestParallelCosignaturesAction(TicketApiModel):
  """Creates one bounded parallel cosignature round for staff members."""

  action: Literal[TicketWorkflowAction.REQUEST_PARALLEL_COSIGNATURES]
  assignee_user_ids: list[UUID] = Field(..., min_length=1, max_length=10)
  comment: str | None = Field(None, max_length=1000)

  @field_validator("assignee_user_ids")
  @classmethod
  def require_distinct_assignees(cls, values: list[UUID]) -> list[UUID]:
    if len(values) != len(set(values)):
      raise ValueError("assigneeUserIds must contain distinct users")
    return values

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class CompleteWorkItemAction(TicketApiModel):
  """Completes exactly one task without implicitly completing its siblings."""

  action: Literal[TicketWorkflowAction.COMPLETE_WORK_ITEM]
  work_item_id: UUID
  outcome: TicketWorkItemOutcome
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class CancelWorkItemAction(TicketApiModel):
  """Cancels one open task that is no longer required by its requester."""

  action: Literal[TicketWorkflowAction.CANCEL_WORK_ITEM]
  work_item_id: UUID
  reason: str | None = Field(None, max_length=1000)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class ForwardTicketAction(TicketApiModel):
  """Transfers current workflow coordination to another staff member."""

  action: Literal[TicketWorkflowAction.FORWARD]
  target_user_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class EscalateTicketAction(TicketApiModel):
  """Requests a decision from one active manager."""

  action: Literal[TicketWorkflowAction.ESCALATE]
  manager_user_id: UUID
  reason: str = Field(..., min_length=3, max_length=1000)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str) -> str:
    return _normalize_required_text(value)


class ApproveEscalationAction(TicketApiModel):
  """Approves the pending escalation and returns the case to its requester."""

  action: Literal[TicketWorkflowAction.APPROVE_ESCALATION]
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class RejectEscalationAction(TicketApiModel):
  """Rejects the pending escalation without rejecting the citizen ticket."""

  action: Literal[TicketWorkflowAction.REJECT_ESCALATION]
  comment: str = Field(..., min_length=3, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str) -> str:
    return _normalize_required_text(value)


class RequestCitizenResponseAction(TicketApiModel):
  """Pauses staff processing until the ticket creator answers a question."""

  action: Literal[TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE]
  question: str = Field(..., min_length=3, max_length=1000)

  @field_validator("question")
  @classmethod
  def normalize_question(cls, value: str) -> str:
    return _normalize_required_text(value)


class ResolveTicketAction(TicketApiModel):
  """Completes a ticket successfully with a citizen-facing explanation."""

  action: Literal[TicketWorkflowAction.RESOLVE]
  message: str = Field(..., min_length=3, max_length=1000)

  @field_validator("message")
  @classmethod
  def normalize_message(cls, value: str) -> str:
    return _normalize_required_text(value)


class RejectTicketAction(TicketApiModel):
  """Ends a ticket as rejected with a citizen-facing explanation."""

  action: Literal[TicketWorkflowAction.REJECT_TICKET]
  message: str = Field(..., min_length=3, max_length=1000)

  @field_validator("message")
  @classmethod
  def normalize_message(cls, value: str) -> str:
    return _normalize_required_text(value)




TicketWorkflowRequest: TypeAlias = Annotated[
  RequestParallelCosignaturesAction
  | CompleteWorkItemAction
  | CancelWorkItemAction
  | ForwardTicketAction
  | EscalateTicketAction
  | ApproveEscalationAction
  | RejectEscalationAction
  | RequestCitizenResponseAction
  | ResolveTicketAction
  | RejectTicketAction,
  Field(discriminator="action"),
]


class TicketAllowedActionsResponse(TicketApiModel):
  """Commands currently available to the requesting staff member."""

  actions: list[TicketWorkflowAction]
  completable_work_item_ids: list[UUID] = Field(default_factory=list)
  cancellable_work_item_ids: list[UUID] = Field(default_factory=list)


class TicketEventResponse(TicketApiModel):
  """Internal chronological event record used by the future authority client."""

  id: UUID
  ticket_id: UUID
  sequence_number: int
  event_type: TicketEventType
  actor_user_id: UUID
  occurred_at: datetime
  payload: dict[str, Any]
  citizen_visible: bool
  public_status: TicketStatus | None = None
  public_message: str | None = None


class TicketWorkItemResponse(TicketApiModel):
  """Projected parallel workflow task returned by later workflow endpoints."""

  id: UUID
  ticket_id: UUID
  group_id: UUID
  kind: TicketWorkItemKind
  status: TicketWorkItemStatus
  outcome: TicketWorkItemOutcome | None = None
  assignee_user_id: UUID
  requested_by_user_id: UUID
  return_to_user_id: UUID
  is_blocking: bool
  comment: str | None = None
  created_at: datetime
  completed_at: datetime | None = None


class TicketInternalDetailResponse(TicketInternalResponse):
  """Internal detail response including projected tasks and allowed commands."""

  work_items: list[TicketWorkItemResponse] = Field(default_factory=list)
  allowed_actions: TicketAllowedActionsResponse


class TicketCitizenResponseRequest(TicketApiModel):
  """Citizen answer to the currently pending authority question."""

  message: str = Field(..., min_length=1, max_length=2000)

  @field_validator("message")
  @classmethod
  def normalize_message(cls, value: str) -> str:
    return _normalize_required_text(value)
