"""Administrative workflow commands and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.request_models import StrictRequestModel
from src.core.validation import NormalizedOptionalText, NormalizedRequiredText
from src.ticket.domain import (
  EscalationDecision,
  TicketCompletionOutcome,
  TicketEventType,
  TicketWorkflowAction,
)
from src.ticket.schemas.ticket import TicketInternalResponse


class TicketDispatchRequest(StrictRequestModel):
  """Dispatcher command that selects the responsible authority."""

  office_id: UUID
  comment: NormalizedOptionalText = Field(None, max_length=1000)


class PrimaryOfficerAssignmentRequest(StrictRequestModel):
  """Manager command that selects or replaces the permanent case owner."""

  primary_officer_id: UUID
  comment: NormalizedOptionalText = Field(None, max_length=1000)


class ForwardTicketAction(StrictRequestModel):
  """Transfers current coordination to another staff member."""

  action: Literal[TicketWorkflowAction.FORWARD]
  target_user_id: UUID
  comment: NormalizedOptionalText = Field(None, max_length=1000)


class RequestCosignatureAction(StrictRequestModel):
  """Temporarily sends the ticket to one selected cosigner."""

  action: Literal[TicketWorkflowAction.REQUEST_COSIGNATURE]
  target_user_id: UUID
  comment: NormalizedOptionalText = Field(None, max_length=1000)


class CosignTicketAction(StrictRequestModel):
  """Records the requested cosignature and returns the case."""

  action: Literal[TicketWorkflowAction.COSIGN]
  comment: NormalizedOptionalText = Field(None, max_length=1000)


class EscalateTicketAction(StrictRequestModel):
  """Requests a decision from one active manager."""

  action: Literal[TicketWorkflowAction.ESCALATE]
  manager_user_id: UUID
  reason: NormalizedRequiredText = Field(..., min_length=3, max_length=1000)


class DecideEscalationAction(StrictRequestModel):
  """Approves or rejects the currently pending escalation."""

  action: Literal[TicketWorkflowAction.DECIDE_ESCALATION]
  decision: EscalationDecision
  comment: NormalizedOptionalText = Field(None, max_length=1000)


class RequestCitizenResponseAction(StrictRequestModel):
  """Pauses staff processing until the citizen answers a question."""

  action: Literal[TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE]
  question: NormalizedRequiredText = Field(..., min_length=3, max_length=1000)


class ReturnToDispatchAction(StrictRequestModel):
  """Returns a wrongly assigned active ticket to the central inbox."""

  action: Literal[TicketWorkflowAction.RETURN_TO_DISPATCH]
  reason: NormalizedRequiredText = Field(..., min_length=3, max_length=1000)


class CompleteTicketAction(StrictRequestModel):
  """Completes a ticket with a resolved or rejected public outcome."""

  action: Literal[TicketWorkflowAction.COMPLETE]
  outcome: TicketCompletionOutcome
  message: NormalizedRequiredText = Field(..., min_length=3, max_length=1000)


TicketWorkflowRequest: TypeAlias = Annotated[
  ForwardTicketAction
  | RequestCosignatureAction
  | CosignTicketAction
  | EscalateTicketAction
  | DecideEscalationAction
  | RequestCitizenResponseAction
  | ReturnToDispatchAction
  | CompleteTicketAction,
  Field(discriminator="action"),
]


class TicketEventResponse(BaseModel):
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


class TicketCitizenResponseRequest(StrictRequestModel):
  """Citizen answer to the currently pending authority question."""

  message: NormalizedRequiredText = Field(..., min_length=1, max_length=2000)
