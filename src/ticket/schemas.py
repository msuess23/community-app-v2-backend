"""Pydantic request and response contracts for the ticket API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.address.schemas import AddressCreate, AddressResponse
from src.ticket.events import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowAction,
  TicketWorkflowState,
  TicketWorkItemKind,
  TicketWorkItemOutcome,
  TicketWorkItemStatus,
)


def _to_camel(value: str) -> str:
  """Converts snake_case field names to the Ktor-compatible camelCase form."""

  head, *tail = value.split("_")
  return head + "".join(part.capitalize() for part in tail)


def _normalize_required_text(value: str) -> str:
  normalized = " ".join(value.split())
  if not normalized:
    raise ValueError("value must not be blank")
  return normalized


def _normalize_optional_text(value: str | None) -> str | None:
  if value is None:
    return None
  normalized = " ".join(value.split())
  return normalized or None


class TicketApiModel(BaseModel):
  """Base model that accepts snake_case and emits camelCase JSON fields."""

  model_config = ConfigDict(
    alias_generator=_to_camel,
    populate_by_name=True,
    from_attributes=True,
  )


class TicketCreateRequest(TicketApiModel):
  """Citizen submission contract derived from the previous Ktor DTO.

  officeId is intentionally absent.  Every new ticket enters the central
  dispatcher inbox and receives its office assignment later in the workflow.
  """

  model_config = ConfigDict(
    alias_generator=_to_camel,
    populate_by_name=True,
    extra="forbid",
  )

  title: str = Field(..., min_length=3, max_length=255)
  description: str | None = Field(None, max_length=5000)
  category: TicketCategory
  address: AddressCreate | None = None
  visibility: TicketVisibility = TicketVisibility.PUBLIC

  @field_validator("title")
  @classmethod
  def normalize_title(cls, value: str) -> str:
    return _normalize_required_text(value)

  @field_validator("description")
  @classmethod
  def normalize_description(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class TicketUpdateRequest(TicketApiModel):
  """Citizen-editable fields while the ticket is still in the NEW state."""

  model_config = ConfigDict(
    alias_generator=_to_camel,
    populate_by_name=True,
    extra="forbid",
  )

  title: str | None = Field(None, min_length=3, max_length=255)
  description: str | None = Field(None, max_length=5000)
  category: TicketCategory | None = None
  address: AddressCreate | None = None
  visibility: TicketVisibility | None = None

  @field_validator("title")
  @classmethod
  def normalize_title(cls, value: str | None) -> str | None:
    return _normalize_required_text(value) if value is not None else None

  @field_validator("description")
  @classmethod
  def normalize_description(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class TicketCancelRequest(TicketApiModel):
  """Optional explanation for cancelling a not-yet-dispatched ticket."""

  reason: str | None = Field(None, max_length=500)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


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


TicketWorkflowRequest: TypeAlias = Annotated[
  RequestParallelCosignaturesAction | CompleteWorkItemAction,
  Field(discriminator="action"),
]


class TicketStatusResponse(TicketApiModel):
  """Citizen-visible status entry compatible with the former Ktor DTO."""

  id: UUID
  status: TicketStatus
  message: str | None = None
  created_by_user_id: UUID | None = None
  created_at: datetime


class TicketResponse(TicketApiModel):
  """Citizen-facing ticket representation preserving the former DTO fields."""

  id: UUID
  title: str
  description: str | None = None
  category: TicketCategory
  office_id: UUID | None = None
  creator_user_id: UUID
  address: AddressResponse | None = None
  visibility: TicketVisibility
  created_at: datetime
  current_status: TicketStatusResponse | None = None
  votes_count: int = 0
  user_voted: bool | None = None
  image_url: str | None = None
  can_edit: bool = False
  version: int


class TicketInternalResponse(TicketResponse):
  """Additional workflow projection fields shown only to administrative users."""

  workflow_state: TicketWorkflowState
  primary_officer_id: UUID | None = None
  current_responsible_user_id: UUID | None = None


class TicketAllowedActionsResponse(TicketApiModel):
  """Commands currently available to the requesting staff member."""

  actions: list[TicketWorkflowAction]
  completable_work_item_ids: list[UUID] = Field(default_factory=list)


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
