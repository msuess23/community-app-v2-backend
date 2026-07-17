"""Citizen-facing ticket request and response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.address.schemas import AddressCreate, AddressResponse
from src.core.validation import normalize_optional_text, normalize_required_text
from src.ticket.domain import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)


class TicketCreateRequest(BaseModel):
  """Citizen submission that enters the central dispatcher inbox."""

  model_config = ConfigDict(extra="forbid")

  title: str = Field(..., min_length=3, max_length=255)
  description: str | None = Field(None, max_length=5000)
  category: TicketCategory
  address: AddressCreate | None = None
  visibility: TicketVisibility = TicketVisibility.PUBLIC

  @field_validator("title")
  @classmethod
  def normalize_title(cls, value: str) -> str:
    """Normalize required title whitespace."""

    return normalize_required_text(value)

  @field_validator("description")
  @classmethod
  def normalize_description(cls, value: str | None) -> str | None:
    """Normalize optional description whitespace."""

    return normalize_optional_text(value)


class TicketUpdateRequest(BaseModel):
  """Citizen-editable fields while the ticket is still new."""

  model_config = ConfigDict(extra="forbid")

  title: str | None = Field(None, min_length=3, max_length=255)
  description: str | None = Field(None, max_length=5000)
  category: TicketCategory | None = None
  address: AddressCreate | None = None
  visibility: TicketVisibility | None = None

  @field_validator("title")
  @classmethod
  def normalize_title(cls, value: str | None) -> str | None:
    """Normalize an optional title when supplied."""

    return normalize_required_text(value) if value is not None else None

  @field_validator("description")
  @classmethod
  def normalize_description(cls, value: str | None) -> str | None:
    """Normalize optional description whitespace."""

    return normalize_optional_text(value)


class TicketCancelRequest(BaseModel):
  """Optional explanation for cancelling a not-yet-dispatched ticket."""

  reason: str | None = Field(None, max_length=500)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str | None) -> str | None:
    """Normalize an optional cancellation reason."""

    return normalize_optional_text(value)


class TicketStatusResponse(BaseModel):
  """Citizen-visible status entry derived from the internal event stream."""

  id: UUID
  status: TicketStatus
  message: str | None = None
  created_by_user_id: UUID | None = None
  created_at: datetime


class TicketResponse(BaseModel):
  """Citizen-facing ticket representation using snake_case API fields."""

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
  """Additional workflow fields shown only to authority users."""

  workflow_state: TicketWorkflowState
  primary_officer_id: UUID | None = None
  current_assignee_id: UUID | None = None
  return_to_user_id: UUID | None = None
