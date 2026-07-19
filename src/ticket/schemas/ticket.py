"""Citizen-facing ticket request and response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.address.schemas import AddressCreate, AddressResponse
from src.core.request_models import StrictRequestModel
from src.core.validation import (
  NonNullableNormalizedUpdateText,
  NormalizedOptionalText,
  NormalizedRequiredText,
)
from src.ticket.domain import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)


class TicketCreateRequest(StrictRequestModel):
  """Citizen submission that enters the central dispatcher inbox."""

  title: NormalizedRequiredText = Field(..., min_length=3, max_length=255)
  description: NormalizedOptionalText = Field(None, max_length=5000)
  category: TicketCategory
  address: AddressCreate | None = None
  visibility: TicketVisibility = TicketVisibility.PUBLIC


class TicketUpdateRequest(StrictRequestModel):
  """Citizen-editable fields while the ticket is still new."""

  title: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=3,
    max_length=255,
  )
  description: NormalizedOptionalText = Field(None, max_length=5000)
  category: TicketCategory | None = None
  address: AddressCreate | None = None
  visibility: TicketVisibility | None = None

  @field_validator("category", "visibility", mode="before")
  @classmethod
  def reject_null_required_update_fields(cls, value: object) -> object:
    """Reject explicit null for enum fields that cannot be cleared."""

    if value is None:
      raise ValueError("category and visibility cannot be null")
    return value


class TicketCancelRequest(StrictRequestModel):
  """Optional explanation for cancelling a not-yet-dispatched ticket."""

  reason: NormalizedOptionalText = Field(None, max_length=500)


class TicketStatusResponse(BaseModel):
  """Citizen-visible status entry derived from the internal event stream."""

  id: UUID
  status: TicketStatus
  message: str | None = None
  created_at: datetime


class TicketResponse(BaseModel):
  """Citizen-facing ticket representation without internal user identifiers."""

  id: UUID
  title: str
  description: str | None = None
  category: TicketCategory
  office_id: UUID | None = None
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

  creator_user_id: UUID
  workflow_state: TicketWorkflowState
  primary_officer_id: UUID | None = None
  current_assignee_id: UUID | None = None
  return_to_user_id: UUID | None = None
