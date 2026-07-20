"""Tests for the reusable immutable PDF storage component."""

from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.exceptions import DomainValidationException
from src.media.document_storage import (
  DocumentStorageConfig,
  DocumentStorageErrorCodes,
  LocalDocumentStorage,
)


def _config(tmp_path) -> DocumentStorageConfig:
  return DocumentStorageConfig(
    root=tmp_path,
    max_bytes=1024 * 1024,
    fallback_filename="document.pdf",
    subject="test",
    errors=DocumentStorageErrorCodes(
      unsupported_type="UNSUPPORTED",
      too_large="TOO_LARGE",
      empty="EMPTY",
      invalid_content="INVALID",
      file_not_found="NOT_FOUND",
    ),
  )


def _upload(content: bytes, *, mime_type: str = "application/pdf") -> UploadFile:
  return UploadFile(
    filename="notice.pdf",
    file=BytesIO(content),
    headers=Headers({"content-type": mime_type}),
  )


@pytest.mark.asyncio
async def test_valid_pdf_is_stored_immutably(tmp_path) -> None:
  stored = await LocalDocumentStorage.save_upload(
    _upload(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"),
    owner_path="owner/group",
    document_id=__import__("uuid").uuid4(),
    config=_config(tmp_path),
  )

  assert stored.mime_type == "application/pdf"
  assert stored.original_filename == "notice.pdf"
  assert stored.storage_key.endswith(".pdf")
  assert LocalDocumentStorage.resolve_file(
    stored.storage_key,
    config=_config(tmp_path),
  ).is_file()


@pytest.mark.asyncio
async def test_declared_pdf_with_invalid_signature_is_removed(tmp_path) -> None:
  with pytest.raises(DomainValidationException) as error:
    await LocalDocumentStorage.save_upload(
      _upload(b"this is not a pdf"),
      owner_path="owner/group",
      document_id=__import__("uuid").uuid4(),
      config=_config(tmp_path),
    )

  assert error.value.error_code == "INVALID"
  assert list(tmp_path.rglob("*.pdf")) == []
