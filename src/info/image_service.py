"""Ordinary CRUD image management for public information notices."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundException
from src.core.transaction_files import (
  register_commit_file_delete,
  register_rollback_file,
  unregister_rollback_file,
)
from src.info.models import Info, InfoImage
from src.info.repository import InfoImageRepository, InfoRepository
from src.info.schemas import InfoImageResponse
from src.info.service import InfoService
from src.media.cover import (
  CoverChange,
  apply_cover_change,
  new_image_should_be_cover,
  plan_cover_after_removal,
  plan_cover_selection,
)
from src.media.storage import (
  ImageStorageConfig,
  ImageStorageErrorCodes,
  LocalImageStorage,
)
from src.user.models import User


class InfoImageService:
  """Manage current Info images without events, revisions or soft deletion."""

  @staticmethod
  def _storage_config() -> ImageStorageConfig:
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

  @staticmethod
  def image_url(info_id: uuid.UUID, image_id: uuid.UUID) -> str:
    return f"{settings.BASE_URL}/infos/{info_id}/images/{image_id}/content"

  @staticmethod
  def _response(image: InfoImage) -> InfoImageResponse:
    return InfoImageResponse(
      id=image.id,
      info_id=image.info_id,
      url=InfoImageService.image_url(image.info_id, image.id),
      original_filename=image.original_filename,
      mime_type=image.mime_type,
      size_bytes=image.size_bytes,
      width=image.width,
      height=image.height,
      uploaded_at=image.uploaded_at,
      is_cover=image.is_cover,
    )

  @staticmethod
  async def _require_info(
    db: AsyncSession,
    info_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> Info:
    info = await InfoRepository.get_by_id(db, info_id, for_update=for_update)
    if info is None:
      raise ResourceNotFoundException(
        "Info not found",
        error_code="INFO_NOT_FOUND",
      )
    return info

  @staticmethod
  async def _apply_cover_change_safely(
    db: AsyncSession,
    images: list[InfoImage],
    change: CoverChange,
  ) -> InfoImage | None:
    """Avoid transient violations of the one-cover partial unique index."""

    if change.changed and change.previous_cover_id is not None:
      previous = next(
        image for image in images if image.id == change.previous_cover_id
      )
      previous.is_cover = False
      await db.flush()
    return apply_cover_change(images, change)

  @staticmethod
  def _existing_path(storage_key: str) -> Path | None:
    try:
      return LocalImageStorage.resolve_file(
        storage_key,
        config=InfoImageService._storage_config(),
      )
    except ResourceNotFoundException:
      # Hard deletion may repair metadata whose physical file is already absent.
      return None

  @staticmethod
  def register_file_deletions(
    db: AsyncSession,
    images: list[InfoImage],
  ) -> None:
    """Schedule owned files for removal only after the database commit succeeds."""

    for image in images:
      path = InfoImageService._existing_path(image.storage_key)
      if path is not None:
        register_commit_file_delete(db, path)

  @staticmethod
  async def list_images(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> list[InfoImageResponse]:
    await InfoImageService._require_info(db, info_id)
    images = await InfoImageRepository.get_images(db, info_id)
    return [InfoImageService._response(image) for image in images]

  @staticmethod
  async def add_image(
    db: AsyncSession,
    info_id: uuid.UUID,
    upload: UploadFile,
    current_user: User,
  ) -> InfoImageResponse:
    info = await InfoImageService._require_info(db, info_id, for_update=True)
    InfoService._require_manage_permission(info, current_user)

    image_id = uuid.uuid4()
    storage_config = InfoImageService._storage_config()
    stored = await LocalImageStorage.save_upload(
      upload,
      owner_path=str(info.id),
      image_id=image_id,
      config=storage_config,
    )
    stored_path = LocalImageStorage.resolve_file(
      stored.storage_key,
      config=storage_config,
    )
    register_rollback_file(db, stored_path)
    images = await InfoImageRepository.get_images(
      db,
      info.id,
      for_update=True,
    )
    image = InfoImage(
      id=image_id,
      info_id=info.id,
      storage_key=stored.storage_key,
      original_filename=stored.original_filename,
      mime_type=stored.mime_type,
      size_bytes=stored.size_bytes,
      width=stored.width,
      height=stored.height,
      uploaded_by_user_id=current_user.id,
      uploaded_at=datetime.now(timezone.utc),
      is_cover=new_image_should_be_cover(images),
    )

    try:
      InfoImageRepository.add(db, image)
      info.updated_at = image.uploaded_at
      await db.flush()
    except Exception:
      LocalImageStorage.delete_file(stored.storage_key, config=storage_config)
      unregister_rollback_file(db, stored_path)
      raise

    return InfoImageService._response(image)

  @staticmethod
  async def set_cover(
    db: AsyncSession,
    info_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User,
  ) -> InfoImageResponse:
    info = await InfoImageService._require_info(db, info_id, for_update=True)
    InfoService._require_manage_permission(info, current_user)
    images = await InfoImageRepository.get_images(
      db,
      info.id,
      for_update=True,
    )
    try:
      change = plan_cover_selection(images, image_id)
    except ValueError as exc:
      raise ResourceNotFoundException(
        "Info image not found",
        error_code="INFO_IMAGE_NOT_FOUND",
      ) from exc

    selected = next(image for image in images if image.id == image_id)
    if not change.changed:
      return InfoImageService._response(selected)

    selected = await InfoImageService._apply_cover_change_safely(
      db,
      images,
      change,
    )
    assert selected is not None
    info.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return InfoImageService._response(selected)

  @staticmethod
  async def delete_image(
    db: AsyncSession,
    info_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User,
  ) -> None:
    info = await InfoImageService._require_info(db, info_id, for_update=True)
    InfoService._require_manage_permission(info, current_user)
    images = await InfoImageRepository.get_images(
      db,
      info.id,
      for_update=True,
    )
    try:
      change = plan_cover_after_removal(images, image_id)
    except ValueError as exc:
      raise ResourceNotFoundException(
        "Info image not found",
        error_code="INFO_IMAGE_NOT_FOUND",
      ) from exc

    image = next(item for item in images if item.id == image_id)
    await InfoImageService._apply_cover_change_safely(db, images, change)
    path = InfoImageService._existing_path(image.storage_key)
    if path is not None:
      register_commit_file_delete(db, path)
    await InfoImageRepository.delete(db, image)
    info.updated_at = datetime.now(timezone.utc)
    await db.flush()

  @staticmethod
  async def get_content(
    db: AsyncSession,
    info_id: uuid.UUID,
    image_id: uuid.UUID,
  ) -> tuple[Path, InfoImage]:
    if await InfoRepository.get_by_id(db, info_id) is None:
      raise ResourceNotFoundException(
        "Info image not found",
        error_code="INFO_IMAGE_NOT_FOUND",
      )
    image = await InfoImageRepository.get_image(db, info_id, image_id)
    if image is None:
      raise ResourceNotFoundException(
        "Info image not found",
        error_code="INFO_IMAGE_NOT_FOUND",
      )
    path = LocalImageStorage.resolve_file(
      image.storage_key,
      config=InfoImageService._storage_config(),
    )
    return path, image
