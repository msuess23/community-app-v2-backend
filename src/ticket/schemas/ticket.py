"""Citizen-facing ticket request and response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from src.address.schemas import AddressCreate, AddressResponse
from src.ticket.events import TicketCategory, TicketStatus, TicketVisibility, TicketWorkflowState
from src.ticket.schemas.base import TicketApiModel, _normalize_optional_text, _normalize_required_text, _to_camel

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
  image_url: str | None = None
  can_edit: bool = False
  can_manage_images: bool = False
  version: int


class TicketInternalResponse(TicketResponse):
  """Additional workflow projection fields shown only to administrative users."""

  workflow_state: TicketWorkflowState
  primary_officer_id: UUID | None = None
  current_responsible_user_id: UUID | None = None
  pending_return_to_user_id: UUID | None = None
