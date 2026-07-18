"""Comment and image API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.core.request_models import StrictRequestModel
from src.core.validation import normalize_optional_text, normalize_required_text
from src.media.schemas import ImageMetadataResponse


class TicketCommentCreateRequest(StrictRequestModel):
  """Create one immutable ticket comment event."""

  text: str = Field(..., min_length=1, max_length=2000)
  is_internal: bool = False

  @field_validator("text")
  @classmethod
  def normalize_text(cls, value: str) -> str:
    """Normalize comment whitespace."""

    return normalize_required_text(value)


class TicketCommentResponse(BaseModel):
  """Comment projection reconstructed directly from a ticket event."""

  id: UUID
  ticket_id: UUID
  text: str
  is_internal: bool
  created_at: datetime


class TicketImageResponse(ImageMetadataResponse):
  """Metadata for one current or historically removed ticket image."""

  ticket_id: UUID
  is_active: bool
  removed_at: datetime | None = None


class TicketImageRemoveRequest(StrictRequestModel):
  """Optional explanation recorded with an image-removal event."""

  reason: str | None = Field(None, max_length=500)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str | None) -> str | None:
    """Normalize an optional removal reason."""

    return normalize_optional_text(value)
