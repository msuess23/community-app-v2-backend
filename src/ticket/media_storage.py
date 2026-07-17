"""Local file storage helpers for revisioned ticket images."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from src.core.config import settings
from src.core.exceptions import DomainValidationException, ResourceNotFoundException


@dataclass(frozen=True)
class StoredTicketImage:
  """Metadata returned after one upload has been streamed to persistent storage."""

  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int


class LocalTicketMediaStorage:
  """Stores ticket images below one configured persistent directory.

  Files use generated names and are never overwritten.  A logical image removal
  only changes the database projection; the bytes remain available for audit
  purposes to authorized authority users.
  """

  CHUNK_SIZE = 64 * 1024
  EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
  }

  @staticmethod
  def _root() -> Path:
    """Returns the normalized storage root and creates it on first use."""

    root = Path(settings.TICKET_MEDIA_ROOT).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root

  @staticmethod
  def _safe_original_filename(filename: str | None) -> str:
    """Removes path components while retaining a useful display filename."""

    normalized = Path(filename or "ticket-image").name.strip()
    return (normalized or "ticket-image")[:255]

  @classmethod
  async def save_upload(
    cls,
    upload: UploadFile,
    *,
    ticket_id: uuid.UUID,
    image_id: uuid.UUID,
  ) -> StoredTicketImage:
    """Streams one validated image to a unique immutable storage key."""

    mime_type = (upload.content_type or "").lower()
    if mime_type not in settings.TICKET_IMAGE_ALLOWED_MIME_TYPES:
      raise DomainValidationException(
        "Unsupported ticket image type.",
        error_code="UNSUPPORTED_TICKET_IMAGE_TYPE",
      )

    extension = cls.EXTENSIONS.get(mime_type)
    if extension is None:
      raise DomainValidationException(
        "No storage extension is configured for this image type.",
        error_code="UNSUPPORTED_TICKET_IMAGE_TYPE",
      )

    storage_key = f"{ticket_id}/{image_id}{extension}"
    target = cls._root() / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    try:
      with target.open("xb") as output:
        while chunk := await upload.read(cls.CHUNK_SIZE):
          total += len(chunk)
          if total > settings.TICKET_IMAGE_MAX_BYTES:
            raise DomainValidationException(
              "Ticket image exceeds the configured size limit.",
              error_code="TICKET_IMAGE_TOO_LARGE",
            )
          output.write(chunk)
    except Exception:
      # A partially written file is never a valid event attachment.
      target.unlink(missing_ok=True)
      raise
    finally:
      await upload.close()

    if total == 0:
      target.unlink(missing_ok=True)
      raise DomainValidationException(
        "Ticket image must not be empty.",
        error_code="EMPTY_TICKET_IMAGE",
      )

    return StoredTicketImage(
      storage_key=storage_key,
      original_filename=cls._safe_original_filename(upload.filename),
      mime_type=mime_type,
      size_bytes=total,
    )

  @classmethod
  def resolve_file(cls, storage_key: str) -> Path:
    """Resolves a stored key while preventing traversal outside the root."""

    root = cls._root()
    path = (root / storage_key).resolve()
    if root not in path.parents:
      raise ResourceNotFoundException(
        "Ticket image not found",
        error_code="TICKET_IMAGE_NOT_FOUND",
      )
    if not path.is_file():
      raise ResourceNotFoundException(
        "Ticket image file not found",
        error_code="TICKET_IMAGE_FILE_NOT_FOUND",
      )
    return path
