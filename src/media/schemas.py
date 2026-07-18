"""Shared API schemas for image metadata."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ImageMetadataResponse(BaseModel):
  """Technical metadata common to images owned by different domains."""

  id: UUID
  url: str
  original_filename: str
  mime_type: str
  size_bytes: int
  width: int | None = None
  height: int | None = None
  uploaded_at: datetime
  is_cover: bool
