"""Comment and image API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.request_models import StrictRequestModel
from src.core.validation import NormalizedOptionalText, NormalizedRequiredText
from src.media.schemas import ImageMetadataResponse


class TicketCommentCreateRequest(StrictRequestModel):
  """Create one immutable ticket comment event."""

  text: NormalizedRequiredText = Field(..., min_length=1, max_length=2000)
  is_internal: bool = False


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

  reason: NormalizedOptionalText = Field(None, max_length=500)
