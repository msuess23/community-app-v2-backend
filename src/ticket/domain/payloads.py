"""Validated payloads stored in the append-only ticket event stream."""

from __future__ import annotations

from typing import Annotated, Any, TypeAlias
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from src.ticket.domain.enums import (
  TicketCategory, TicketEventType, TicketVisibility, TicketWorkItemKind,
  TicketWorkItemOutcome,
)

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


def validate_event_payload(
  event_type: TicketEventType,
  payload: BaseModel | dict[str, Any],
) -> EventPayload:
  """Validates a payload against the schema assigned to its event type."""

  payload_type = _EVENT_PAYLOAD_TYPES[event_type]
  return TypeAdapter(payload_type).validate_python(payload)
