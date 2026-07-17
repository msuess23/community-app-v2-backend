"""Comment and image API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from src.ticket.schemas.base import TicketApiModel, _normalize_optional_text, _normalize_required_text

class TicketCommentCreateRequest(TicketApiModel):
  """Creates one immutable ticket comment event."""

  text: str = Field(..., min_length=1, max_length=2000)
  is_internal: bool = False

  @field_validator("text")
  @classmethod
  def normalize_text(cls, value: str) -> str:
    return _normalize_required_text(value)


class TicketCommentResponse(TicketApiModel):
  """Comment projection reconstructed directly from a ticket event."""

  id: UUID
  ticket_id: UUID
  text: str
  is_internal: bool
  author_user_id: UUID
  created_at: datetime


class TicketImageResponse(TicketApiModel):
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


class TicketImageRemoveRequest(TicketApiModel):
  """Optional explanation recorded with an image-removal event."""

  reason: str | None = Field(None, max_length=500)

  @field_validator("reason")
  @classmethod
  def normalize_reason(cls, value: str | None) -> str | None:
    return _normalize_optional_text(value)
