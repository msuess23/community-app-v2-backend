from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers

from src.core.exceptions import DomainValidationException
from src.media.storage import (
  ImageStorageConfig,
  ImageStorageErrorCodes,
  LocalImageStorage,
)


def _config(root: Path) -> ImageStorageConfig:
  return ImageStorageConfig(
    root=root,
    max_bytes=1024 * 1024,
    allowed_mime_types=frozenset({"image/jpeg", "image/png", "image/webp"}),
    fallback_filename="image",
    subject="test",
    errors=ImageStorageErrorCodes(
      unsupported_type="UNSUPPORTED_TEST_IMAGE_TYPE",
      too_large="TEST_IMAGE_TOO_LARGE",
      empty="EMPTY_TEST_IMAGE",
      invalid_content="INVALID_TEST_IMAGE_CONTENT",
      type_mismatch="TEST_IMAGE_TYPE_MISMATCH",
      invalid_dimensions="INVALID_TEST_IMAGE_DIMENSIONS",
      file_not_found="TEST_IMAGE_FILE_NOT_FOUND",
    ),
  )


def _image_bytes(*, image_format: str, size: tuple[int, int]) -> bytes:
  output = BytesIO()
  Image.new("RGB", size).save(output, format=image_format)
  return output.getvalue()


@pytest.mark.asyncio
async def test_storage_validates_content_and_returns_dimensions(tmp_path) -> None:
  content = _image_bytes(image_format="JPEG", size=(12, 8))
  upload = UploadFile(
    file=BytesIO(content),
    filename="../damage.jpg",
    headers=Headers({"content-type": "image/jpeg"}),
  )

  stored = await LocalImageStorage.save_upload(
    upload,
    owner_path="tickets/example",
    image_id=uuid4(),
    config=_config(tmp_path),
  )

  assert stored.original_filename == "damage.jpg"
  assert stored.mime_type == "image/jpeg"
  assert stored.size_bytes == len(content)
  assert (stored.width, stored.height) == (12, 8)
  assert (tmp_path / stored.storage_key).read_bytes() == content


@pytest.mark.asyncio
async def test_storage_rejects_invalid_binary_content(tmp_path) -> None:
  upload = UploadFile(
    file=BytesIO(b"not-an-image"),
    filename="fake.jpg",
    headers=Headers({"content-type": "image/jpeg"}),
  )

  with pytest.raises(DomainValidationException) as error:
    await LocalImageStorage.save_upload(
      upload,
      owner_path="tickets/example",
      image_id=uuid4(),
      config=_config(tmp_path),
    )

  assert error.value.error_code == "INVALID_TEST_IMAGE_CONTENT"
  assert not list(tmp_path.rglob("*.jpg"))


@pytest.mark.asyncio
async def test_storage_rejects_declared_type_mismatch(tmp_path) -> None:
  upload = UploadFile(
    file=BytesIO(_image_bytes(image_format="PNG", size=(4, 4))),
    filename="fake.jpg",
    headers=Headers({"content-type": "image/jpeg"}),
  )

  with pytest.raises(DomainValidationException) as error:
    await LocalImageStorage.save_upload(
      upload,
      owner_path="tickets/example",
      image_id=uuid4(),
      config=_config(tmp_path),
    )

  assert error.value.error_code == "TEST_IMAGE_TYPE_MISMATCH"
  assert not list(tmp_path.rglob("*.jpg"))
