"""Generic immutable local image storage with content validation."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from src.core.exceptions import DomainValidationException, ResourceNotFoundException
from src.core.file_storage import LocalFileStorage


_IMAGE_FORMAT_TO_MIME_TYPE = {
  "JPEG": "image/jpeg",
  "PNG": "image/png",
  "WEBP": "image/webp",
}

_IMAGE_EXTENSIONS = {
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp",
}


@dataclass(frozen=True)
class ImageStorageErrorCodes:
  """Domain-specific error codes emitted by the shared storage component."""

  unsupported_type: str
  too_large: str
  empty: str
  invalid_content: str
  type_mismatch: str
  invalid_dimensions: str
  file_not_found: str


@dataclass(frozen=True)
class ImageStorageConfig:
  """Domain-provided limits, labels and errors for one image collection."""

  root: str | Path
  max_bytes: int
  allowed_mime_types: frozenset[str]
  fallback_filename: str
  subject: str
  errors: ImageStorageErrorCodes


@dataclass(frozen=True)
class StoredImage:
  """Validated metadata returned after one immutable image upload."""

  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int
  width: int
  height: int


class LocalImageStorage:
  """Store immutable images while validating their actual binary content."""

  @classmethod
  def _inspect_image(
    cls,
    path: Path,
    *,
    declared_mime_type: str,
    config: ImageStorageConfig,
  ) -> tuple[str, int, int]:
    """Validate the file signature and return canonical MIME type and dimensions."""

    try:
      with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
          image.verify()
        with Image.open(path) as image:
          image_format = image.format
          width, height = image.size
    except (
      Image.DecompressionBombError,
      Image.DecompressionBombWarning,
      UnidentifiedImageError,
      OSError,
      ValueError,
    ) as exc:
      raise DomainValidationException(
        f"Uploaded file is not a valid {config.subject} image.",
        error_code=config.errors.invalid_content,
      ) from exc

    actual_mime_type = _IMAGE_FORMAT_TO_MIME_TYPE.get(image_format or "")
    if (
      actual_mime_type is None
      or actual_mime_type not in config.allowed_mime_types
      or actual_mime_type != declared_mime_type
    ):
      raise DomainValidationException(
        f"Declared {config.subject} image type does not match the uploaded file.",
        error_code=config.errors.type_mismatch,
      )

    if width <= 0 or height <= 0:
      raise DomainValidationException(
        f"Uploaded {config.subject} image dimensions are invalid.",
        error_code=config.errors.invalid_dimensions,
      )

    return actual_mime_type, width, height

  @classmethod
  async def save_upload(
    cls,
    upload: UploadFile,
    *,
    owner_path: str,
    image_id: UUID,
    config: ImageStorageConfig,
  ) -> StoredImage:
    """Stream, validate and retain one immutable image file.

    ``owner_path`` is deliberately opaque to the storage layer. Ticket and Info
    services can therefore choose stable per-entity directory layouts without
    introducing target-type switches into this shared component.
    """

    stored = await LocalFileStorage.save_upload(
      upload,
      root=config.root,
      storage_key_without_extension=f"{owner_path}/{image_id}",
      allowed_mime_types=set(config.allowed_mime_types),
      extensions=_IMAGE_EXTENSIONS,
      max_bytes=config.max_bytes,
      fallback_filename=config.fallback_filename,
      unsupported_message=f"Unsupported {config.subject} image type.",
      unsupported_error_code=config.errors.unsupported_type,
      too_large_message=f"{config.subject.title()} image exceeds the configured size limit.",
      too_large_error_code=config.errors.too_large,
      empty_message=f"{config.subject.title()} image must not be empty.",
      empty_error_code=config.errors.empty,
    )

    path = cls._resolve_file(stored.storage_key, config=config)
    try:
      mime_type, width, height = cls._inspect_image(
        path,
        declared_mime_type=stored.mime_type,
        config=config,
      )
    except Exception:
      path.unlink(missing_ok=True)
      raise

    return StoredImage(
      storage_key=stored.storage_key,
      original_filename=stored.original_filename,
      mime_type=mime_type,
      size_bytes=stored.size_bytes,
      width=width,
      height=height,
    )

  @staticmethod
  def _resolve_file(
    storage_key: str,
    *,
    config: ImageStorageConfig,
  ) -> Path:
    """Resolve a file with the configured domain-specific not-found error."""

    return LocalFileStorage.resolve_file(
      root=config.root,
      storage_key=storage_key,
      not_found_message=f"{config.subject.title()} image file not found",
      not_found_error_code=config.errors.file_not_found,
    )

  @classmethod
  def resolve_file(
    cls,
    storage_key: str,
    *,
    config: ImageStorageConfig,
  ) -> Path:
    """Resolve a stored image without allowing traversal outside its root."""

    return cls._resolve_file(storage_key, config=config)

  @classmethod
  def delete_file(
    cls,
    storage_key: str,
    *,
    config: ImageStorageConfig,
  ) -> None:
    """Delete a newly written file when its owning transaction cannot be staged."""

    try:
      path = cls._resolve_file(storage_key, config=config)
    except ResourceNotFoundException:
      return
    path.unlink(missing_ok=True)
