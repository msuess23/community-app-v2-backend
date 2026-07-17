"""Comment and image API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.core.validation import normalize_optional_text, normalize_required_text


class TicketCommentCreateRequest(BaseModel):
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
  author_user_id: UUID
  created_at: datetime


class TicketImageResponse(BaseModel):
  """Metadata for one current or historically removed ticket image."""

  id: UUID
  ticket_id: UUID
  url: str
  original_filename: str
  mime_type: str
  size_bytes: int
  uploaded_by_user_id: UUID
  uploaded_at: datetime
  is_active: bool
  is_cover: bool
  removed_at: datetime | None = None


class TicketImageRemoveRequest(BaseModel):
  """Optional explanation recorded with an image-removal event."""

  reason: str | None = Field(None, max_length=500)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str | None) -> str | None:
    """Normalize an optional removal reason."""

    return normalize_optional_text(value)
