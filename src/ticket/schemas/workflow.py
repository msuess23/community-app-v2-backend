"""Administrative workflow commands and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import Field, field_validator

from src.ticket.events import (
  EscalationDecision,
  TicketCompletionOutcome,
  TicketEventType,
  TicketWorkflowAction,
)
from src.ticket.schemas.base import (
  TicketApiModel,
  _normalize_optional_text,
  _normalize_required_text,
)
from src.ticket.schemas.ticket import TicketInternalResponse


class TicketDispatchRequest(TicketApiModel):
  """Dispatcher command that selects the responsible authority."""

  office_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class PrimaryOfficerAssignmentRequest(TicketApiModel):
  """Manager command that selects the permanent case owner."""

  primary_officer_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class ForwardTicketAction(TicketApiModel):
  """Transfers current coordination to another staff member."""

  action: Literal[TicketWorkflowAction.FORWARD]
  target_user_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class RequestCosignatureAction(TicketApiModel):
  """Temporarily sends the ticket to one selected cosigner."""

  action: Literal[TicketWorkflowAction.REQUEST_COSIGNATURE]
  target_user_id: UUID
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class CosignTicketAction(TicketApiModel):
  """Records the requested cosignature and returns the case."""

  action: Literal[TicketWorkflowAction.COSIGN]
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


class DecideEscalationAction(TicketApiModel):
  """Approves or rejects the currently pending escalation."""

  action: Literal[TicketWorkflowAction.DECIDE_ESCALATION]
  decision: EscalationDecision
  comment: str | None = Field(None, max_length=1000)

  @field_validator("comment")
  @classmethod
  def normalize_comment(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)


class RequestCitizenResponseAction(TicketApiModel):
  """Pauses staff processing until the citizen answers a question."""

  action: Literal[TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE]
  question: str = Field(..., min_length=3, max_length=1000)

  @field_validator("question")
  @classmethod
  def normalize_question(cls, value: str) -> str:
    return _normalize_required_text(value)


class CompleteTicketAction(TicketApiModel):
  """Completes a ticket with a resolved or rejected public outcome."""

  action: Literal[TicketWorkflowAction.COMPLETE]
  outcome: TicketCompletionOutcome
  message: str = Field(..., min_length=3, max_length=1000)

  @field_validator("message")
  @classmethod
  def normalize_message(cls, value: str) -> str:
    return _normalize_required_text(value)


TicketWorkflowRequest: TypeAlias = Annotated[
  ForwardTicketAction
  | RequestCosignatureAction
  | CosignTicketAction
  | EscalateTicketAction
  | DecideEscalationAction
  | RequestCitizenResponseAction
  | CompleteTicketAction,
  Field(discriminator="action"),
]


class TicketEventResponse(TicketApiModel):
  """Internal chronological event record used by the authority client."""

  id: UUID
  ticket_id: UUID
  sequence_number: int
  event_type: TicketEventType
  actor_user_id: UUID
  occurred_at: datetime
  payload: dict[str, Any]


class TicketInternalDetailResponse(TicketInternalResponse):
  """Internal detail response including commands currently allowed."""

  allowed_actions: list[TicketWorkflowAction] = Field(default_factory=list)


class TicketCitizenResponseRequest(TicketApiModel):
  """Citizen answer to the currently pending authority question."""

  message: str = Field(..., min_length=1, max_length=2000)

  @field_validator("message")
  @classmethod
  def normalize_message(cls, value: str) -> str:
    return _normalize_required_text(value)
