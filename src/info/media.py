"""Info-specific configuration and filesystem helpers for shared image media."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from src.core.config import settings
from src.core.exceptions import ResourceNotFoundException
from src.core.transaction_files import register_commit_file_delete
from src.info.models import InfoImage
from src.media.storage import (
  ImageStorageConfig,
  ImageStorageErrorCodes,
  LocalImageStorage,
)


def info_image_storage_config() -> ImageStorageConfig:
  """Build the Info image configuration from the current application settings."""

  return ImageStorageConfig(
    root=settings.INFO_MEDIA_ROOT,
    max_bytes=settings.INFO_IMAGE_MAX_BYTES,
    allowed_mime_types=frozenset(settings.INFO_IMAGE_ALLOWED_MIME_TYPES),
    fallback_filename="info-image",
    subject="info",
    errors=ImageStorageErrorCodes(
      unsupported_type="UNSUPPORTED_INFO_IMAGE_TYPE",
      too_large="INFO_IMAGE_TOO_LARGE",
      empty="EMPTY_INFO_IMAGE",
      invalid_content="INVALID_INFO_IMAGE_CONTENT",
      type_mismatch="INFO_IMAGE_TYPE_MISMATCH",
      invalid_dimensions="INVALID_INFO_IMAGE_DIMENSIONS",
      file_not_found="INFO_IMAGE_FILE_NOT_FOUND",
    ),
  )


def info_image_content_url(info_id: uuid.UUID, image_id: uuid.UUID) -> str:
  """Return the stable canonical API URL for one Info image."""

  return f"{settings.BASE_URL}/infos/{info_id}/images/{image_id}/content"


def resolve_existing_info_image_path(storage_key: str) -> Path | None:
  """Resolve an existing file while allowing metadata-only cleanup repairs."""

  try:
    return LocalImageStorage.resolve_file(
      storage_key,
      config=info_image_storage_config(),
    )
  except ResourceNotFoundException:
    return None


def register_info_file_deletions(
  db: AsyncSession,
  images: list[InfoImage],
) -> None:
  """Delete owned image files only after the surrounding transaction commits."""

  for image in images:
    path = resolve_existing_info_image_path(image.storage_key)
    if path is not None:
      register_commit_file_delete(db, path)
