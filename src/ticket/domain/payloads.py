"""Validated payloads stored in the append-only ticket event stream."""

from __future__ import annotations

from typing import Any, TypeAlias
from uuid import UUID

from pydantic import BaseModel, TypeAdapter

from src.address.snapshot import AddressSnapshot

from src.ticket.domain.enums import (
  EscalationDecision,
  TicketCategory,
  TicketCompletionOutcome,
  TicketEventType,
  TicketVisibility,
)



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
  """Moves overall coordination without changing permanent ownership."""

  target_user_id: UUID
  comment: str | None = None


class CosignatureRequestedPayload(BaseModel):
  """Temporarily sends the ticket to one employee for sequential cosigning."""

  target_user_id: UUID
  return_to_user_id: UUID
  comment: str | None = None


class TicketCosignedPayload(BaseModel):
  """Records a cosignature and returns the ticket to its requester."""

  return_to_user_id: UUID
  comment: str | None = None


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
  """Stores one management decision and the employee receiving the case back."""

  return_to_user_id: UUID
  decision: EscalationDecision
  comment: str | None = None


class TicketCompletedPayload(BaseModel):
  """Stores the terminal outcome and citizen-facing explanation."""

  outcome: TicketCompletionOutcome
  message: str


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
  width: int | None = None
  height: int | None = None
  is_cover: bool


class TicketImageRemovedPayload(BaseModel):
  """Marks a projected image as removed without deleting its stored file."""

  image_id: UUID
  reason: str | None = None


class TicketCoverImageChangedPayload(BaseModel):
  """Select the image represented by the ticket cover URL."""

  image_id: UUID


EventPayload: TypeAlias = (
  TicketSubmittedPayload
  | TicketDetailsUpdatedPayload
  | TicketCancelledPayload
  | TicketDispatchedPayload
  | PrimaryOfficerAssignedPayload
  | TicketForwardedPayload
  | CosignatureRequestedPayload
  | TicketCosignedPayload
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
  TicketEventType.COSIGNATURE_REQUESTED: CosignatureRequestedPayload,
  TicketEventType.TICKET_COSIGNED: TicketCosignedPayload,
  TicketEventType.CITIZEN_RESPONSE_REQUESTED: CitizenResponseRequestedPayload,
  TicketEventType.CITIZEN_RESPONDED: CitizenRespondedPayload,
  TicketEventType.TICKET_ESCALATED: TicketEscalatedPayload,
  TicketEventType.ESCALATION_DECIDED: EscalationDecisionPayload,
  TicketEventType.TICKET_COMPLETED: TicketCompletedPayload,
  TicketEventType.TICKET_COMMENTED: TicketCommentedPayload,
  TicketEventType.TICKET_IMAGE_ADDED: TicketImageAddedPayload,
  TicketEventType.TICKET_IMAGE_REMOVED: TicketImageRemovedPayload,
  TicketEventType.TICKET_COVER_IMAGE_CHANGED: TicketCoverImageChangedPayload,
}


def validate_event_payload(
  event_type: TicketEventType,
  payload: BaseModel | dict[str, Any],
) -> EventPayload:
  """Validates a payload against the schema assigned to its event type."""

  payload_type = _EVENT_PAYLOAD_TYPES[event_type]
  return TypeAdapter(payload_type).validate_python(payload)
