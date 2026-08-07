"""Generic immutable PDF storage built on the shared file-storage primitive."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from src.core.exceptions import DomainValidationException, ResourceNotFoundException
from src.core.file_storage import LocalFileStorage


@dataclass(frozen=True)
class DocumentStorageErrorCodes:
  """Domain-specific errors emitted by the reusable document store."""

  unsupported_type: str
  too_large: str
  empty: str
  invalid_content: str
  file_not_found: str


@dataclass(frozen=True)
class DocumentStorageConfig:
  """Limits, labels and paths supplied by one document-owning domain."""

  root: str | Path
  max_bytes: int
  fallback_filename: str
  subject: str
  errors: DocumentStorageErrorCodes


@dataclass(frozen=True)
class StoredDocument:
  """Validated immutable metadata returned after one PDF upload."""

  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int


class LocalDocumentStorage:
  """Store immutable PDF documents and validate their binary signatures."""

  MIME_TYPE = "application/pdf"
  EXTENSION = ".pdf"

  @staticmethod
  def _inspect_pdf(path: Path, *, config: DocumentStorageConfig) -> None:
    """Reject files that do not have a plausible PDF header and trailer."""

    try:
      with path.open("rb") as document:
        header = document.read(8)
        document.seek(0, 2)
        size = document.tell()
        document.seek(max(0, size - 4096))
        trailer = document.read()
    except OSError as exc:
      raise DomainValidationException(
        f"Uploaded file is not a valid {config.subject} PDF.",
        error_code=config.errors.invalid_content,
      ) from exc

    if not header.startswith(b"%PDF-") or b"%%EOF" not in trailer:
      raise DomainValidationException(
        f"Uploaded file is not a valid {config.subject} PDF.",
        error_code=config.errors.invalid_content,
      )

  @classmethod
  async def save_upload(
    cls,
    upload: UploadFile,
    *,
    owner_path: str,
    document_id: UUID,
    config: DocumentStorageConfig,
  ) -> StoredDocument:
    """Stream, validate and retain one immutable PDF document."""

    stored = await LocalFileStorage.save_upload(
      upload,
      root=config.root,
      storage_key_without_extension=f"{owner_path}/{document_id}",
      allowed_mime_types={cls.MIME_TYPE},
      extensions={cls.MIME_TYPE: cls.EXTENSION},
      max_bytes=config.max_bytes,
      fallback_filename=config.fallback_filename,
      unsupported_message=f"Unsupported {config.subject} document type.",
      unsupported_error_code=config.errors.unsupported_type,
      too_large_message=(
        f"{config.subject.title()} document exceeds the configured size limit."
      ),
      too_large_error_code=config.errors.too_large,
      empty_message=f"{config.subject.title()} document must not be empty.",
      empty_error_code=config.errors.empty,
    )

    path = cls._resolve_file(stored.storage_key, config=config)
    try:
      cls._inspect_pdf(path, config=config)
    except Exception:
      path.unlink(missing_ok=True)
      raise

    return StoredDocument(
      storage_key=stored.storage_key,
      original_filename=stored.original_filename,
      mime_type=cls.MIME_TYPE,
      size_bytes=stored.size_bytes,
    )

  @staticmethod
  def _resolve_file(
    storage_key: str,
    *,
    config: DocumentStorageConfig,
  ) -> Path:
    """Resolve a document using the domain-specific not-found contract."""

    return LocalFileStorage.resolve_file(
      root=config.root,
      storage_key=storage_key,
      not_found_message=f"{config.subject.title()} document file not found",
      not_found_error_code=config.errors.file_not_found,
    )

  @classmethod
  def resolve_file(
    cls,
    storage_key: str,
    *,
    config: DocumentStorageConfig,
  ) -> Path:
    """Resolve a stored document without permitting path traversal."""

    return cls._resolve_file(storage_key, config=config)

  @classmethod
  def delete_file(
    cls,
    storage_key: str,
    *,
    config: DocumentStorageConfig,
  ) -> None:
    """Delete a newly written file when its owning transaction fails."""

    try:
      path = cls._resolve_file(storage_key, config=config)
    except ResourceNotFoundException:
      return
    path.unlink(missing_ok=True)
