"""Ticket-specific configuration wrapper around the generic local file store."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from src.core.config import settings
from src.core.file_storage import LocalFileStorage


@dataclass(frozen=True)
class StoredTicketImage:
  """Metadata returned after one ticket image upload."""

  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int


class LocalTicketMediaStorage:
  """Stores immutable ticket images using ticket-specific validation settings."""

  EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
  }

  @classmethod
  async def save_upload(
    cls,
    upload: UploadFile,
    *,
    ticket_id: uuid.UUID,
    image_id: uuid.UUID,
  ) -> StoredTicketImage:
    """Streams one ticket image to a unique, never-overwritten storage key."""

    stored = await LocalFileStorage.save_upload(
      upload,
      root=settings.TICKET_MEDIA_ROOT,
      storage_key_without_extension=f"{ticket_id}/{image_id}",
      allowed_mime_types=settings.TICKET_IMAGE_ALLOWED_MIME_TYPES,
      extensions=cls.EXTENSIONS,
      max_bytes=settings.TICKET_IMAGE_MAX_BYTES,
      fallback_filename="ticket-image",
      unsupported_message="Unsupported ticket image type.",
      unsupported_error_code="UNSUPPORTED_TICKET_IMAGE_TYPE",
      too_large_message="Ticket image exceeds the configured size limit.",
      too_large_error_code="TICKET_IMAGE_TOO_LARGE",
      empty_message="Ticket image must not be empty.",
      empty_error_code="EMPTY_TICKET_IMAGE",
    )
    return StoredTicketImage(**stored.__dict__)

  @classmethod
  def resolve_file(cls, storage_key: str) -> Path:
    """Resolves a stored ticket image without allowing path traversal."""

    return LocalFileStorage.resolve_file(
      root=settings.TICKET_MEDIA_ROOT,
      storage_key=storage_key,
      not_found_message="Ticket image file not found",
      not_found_error_code="TICKET_IMAGE_FILE_NOT_FOUND",
    )
