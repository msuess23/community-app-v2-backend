"""Reusable local storage primitives for immutable uploaded files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from fastapi import UploadFile

from src.core.exceptions import DomainValidationException, ResourceNotFoundException


@dataclass(frozen=True)
class StoredFile:
  """Metadata returned after an upload has been streamed to local storage."""

  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int


class LocalFileStorage:
  """Streams immutable uploads below a configured persistent root directory."""

  CHUNK_SIZE = 64 * 1024

  @staticmethod
  def ensure_root(root: str | Path) -> Path:
    """Creates and returns a normalized storage root."""

    normalized = Path(root).expanduser().resolve()
    normalized.mkdir(parents=True, exist_ok=True)
    return normalized

  @staticmethod
  def safe_filename(filename: str | None, *, fallback: str) -> str:
    """Removes path components while retaining a useful display filename."""

    normalized = Path(filename or fallback).name.strip()
    return (normalized or fallback)[:255]

  @classmethod
  async def save_upload(
    cls,
    upload: UploadFile,
    *,
    root: str | Path,
    storage_key_without_extension: str,
    allowed_mime_types: set[str],
    extensions: Mapping[str, str],
    max_bytes: int,
    fallback_filename: str,
    unsupported_message: str,
    unsupported_error_code: str,
    too_large_message: str,
    too_large_error_code: str,
    empty_message: str,
    empty_error_code: str,
  ) -> StoredFile:
    """Validates and streams one immutable file to a generated storage key."""

    mime_type = (upload.content_type or "").lower()
    if mime_type not in allowed_mime_types or mime_type not in extensions:
      raise DomainValidationException(
        unsupported_message,
        error_code=unsupported_error_code,
      )

    storage_key = f"{storage_key_without_extension}{extensions[mime_type]}"
    target = cls.ensure_root(root) / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    try:
      with target.open("xb") as output:
        while chunk := await upload.read(cls.CHUNK_SIZE):
          total += len(chunk)
          if total > max_bytes:
            raise DomainValidationException(
              too_large_message,
              error_code=too_large_error_code,
            )
          output.write(chunk)
    except Exception:
      target.unlink(missing_ok=True)
      raise
    finally:
      await upload.close()

    if total == 0:
      target.unlink(missing_ok=True)
      raise DomainValidationException(empty_message, error_code=empty_error_code)

    return StoredFile(
      storage_key=storage_key,
      original_filename=cls.safe_filename(upload.filename, fallback=fallback_filename),
      mime_type=mime_type,
      size_bytes=total,
    )

  @classmethod
  def resolve_file(
    cls,
    *,
    root: str | Path,
    storage_key: str,
    not_found_message: str,
    not_found_error_code: str,
  ) -> Path:
    """Resolves a storage key while preventing traversal outside the root."""

    normalized_root = cls.ensure_root(root)
    path = (normalized_root / storage_key).resolve()
    if normalized_root not in path.parents or not path.is_file():
      raise ResourceNotFoundException(
        not_found_message,
        error_code=not_found_error_code,
      )
    return path
