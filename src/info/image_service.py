"""Ordinary CRUD image management for public information notices."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.exceptions import ResourceNotFoundException
from src.core.transaction_files import register_rollback_file, unregister_rollback_file
from src.info.access_policy import InfoAccessPolicy
from src.info.mapper import InfoResponseMapper
from src.info.media import (
  info_image_storage_config,
  register_info_file_deletions,
)
from src.info.models import Info, InfoImage
from src.info.repository import InfoImageRepository, InfoRepository
from src.info.schemas import InfoImageResponse
from src.media.cover import (
  new_image_should_be_cover,
  plan_cover_after_removal,
  plan_cover_selection,
)
from src.media.cover_persistence import apply_cover_change_safely
from src.media.storage import LocalImageStorage
from src.user.models import User


class InfoImageService:
  """Manage current Info images without events, revisions or soft deletion."""

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
  async def list_images(
    db: AsyncSession,
    info_id: uuid.UUID,
  ) -> list[InfoImageResponse]:
    await InfoImageService._require_info(db, info_id)
    images = await InfoImageRepository.get_images(db, info_id)
    return [InfoResponseMapper.image_response(image) for image in images]

  @staticmethod
  async def add_image(
    db: AsyncSession,
    info_id: uuid.UUID,
    upload: UploadFile,
    current_user: User,
  ) -> InfoImageResponse:
    info = await InfoImageService._require_info(db, info_id, for_update=True)
    InfoAccessPolicy.require_manage_permission(info, current_user)

    image_id = uuid.uuid4()
    storage_config = info_image_storage_config()
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

    return InfoResponseMapper.image_response(image)

  @staticmethod
  async def set_cover(
    db: AsyncSession,
    info_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User,
  ) -> InfoImageResponse:
    info = await InfoImageService._require_info(db, info_id, for_update=True)
    InfoAccessPolicy.require_manage_permission(info, current_user)
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
      return InfoResponseMapper.image_response(selected)

    selected = await apply_cover_change_safely(
      db,
      images,
      change,
    )
    assert selected is not None
    info.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return InfoResponseMapper.image_response(selected)

  @staticmethod
  async def delete_image(
    db: AsyncSession,
    info_id: uuid.UUID,
    image_id: uuid.UUID,
    current_user: User,
  ) -> None:
    info = await InfoImageService._require_info(db, info_id, for_update=True)
    InfoAccessPolicy.require_manage_permission(info, current_user)
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
    await apply_cover_change_safely(db, images, change)
    register_info_file_deletions(db, [image])
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
      config=info_image_storage_config(),
    )
    return path, image
