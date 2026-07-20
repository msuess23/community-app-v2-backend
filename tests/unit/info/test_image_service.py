from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.core.transaction_files import cleanup_commit_file_deletes
from src.info.image_service import InfoImageService
from src.info.models import Info, InfoCategory, InfoImage, InfoStatus
from src.info.repository import InfoImageRepository, InfoRepository
from src.media.storage import StoredImage
from src.user.models import Role, User


def _db() -> MagicMock:
  db = MagicMock()
  db.info = {}
  db.flush = AsyncMock()
  return db


def _manager(office_id):
  return User(
    id=uuid4(),
    email=f"{uuid4()}@example.com",
    hashed_password="hash",
    first_name="Info",
    last_name="Manager",
    role=Role.MANAGER,
    office_id=office_id,
    is_active=True,
  )


def _info(office_id):
  now = datetime.now(timezone.utc)
  return Info(
    id=uuid4(),
    title="Public notice",
    category=InfoCategory.ANNOUNCEMENT,
    office_id=office_id,
    current_status=InfoStatus.SCHEDULED,
    created_at=now,
    updated_at=now,
    starts_at=now + timedelta(days=1),
    ends_at=now + timedelta(days=2),
    images=[],
  )


def _image(info, uploader, *, is_cover, suffix):
  return InfoImage(
    id=uuid4(),
    info_id=info.id,
    storage_key=f"{info.id}/{suffix}.png",
    original_filename=f"{suffix}.png",
    mime_type="image/png",
    size_bytes=100,
    width=20,
    height=10,
    uploaded_by_user_id=uploader.id,
    uploaded_at=datetime.now(timezone.utc),
    is_cover=is_cover,
  )


@pytest.mark.asyncio
async def test_first_upload_becomes_cover_without_event_metadata(
  monkeypatch,
  tmp_path,
) -> None:
  office_id = uuid4()
  manager = _manager(office_id)
  info = _info(office_id)
  db = _db()
  staged: list[InfoImage] = []
  stored_path = tmp_path / "stored.png"
  stored_path.write_bytes(b"image")

  monkeypatch.setattr(
    InfoRepository,
    "get_by_id",
    AsyncMock(return_value=info),
  )
  monkeypatch.setattr(
    InfoImageRepository,
    "get_images",
    AsyncMock(return_value=[]),
  )
  monkeypatch.setattr(
    InfoImageRepository,
    "add",
    lambda _db, image: staged.append(image),
  )
  monkeypatch.setattr(
    "src.info.image_service.LocalImageStorage.save_upload",
    AsyncMock(
      return_value=StoredImage(
        storage_key=f"{info.id}/stored.png",
        original_filename="notice.png",
        mime_type="image/png",
        size_bytes=100,
        width=20,
        height=10,
      )
    ),
  )
  monkeypatch.setattr(
    "src.info.image_service.LocalImageStorage.resolve_file",
    lambda *args, **kwargs: stored_path,
  )

  response = await InfoImageService.add_image(
    db,
    info.id,
    object(),
    manager,
  )

  assert response.info_id == info.id
  assert response.is_cover is True
  assert response.url.endswith(f"/{response.id}/content")
  assert len(staged) == 1
  assert staged[0].is_cover is True
  assert "added_event_id" not in InfoImage.__table__.c
  assert stored_path.resolve() in db.info["rollback_file_paths"]


@pytest.mark.asyncio
async def test_deleting_cover_physically_removes_row_and_selects_replacement(
  monkeypatch,
  tmp_path,
) -> None:
  office_id = uuid4()
  manager = _manager(office_id)
  info = _info(office_id)
  first = _image(info, manager, is_cover=True, suffix="first")
  second = _image(info, manager, is_cover=False, suffix="second")
  info.images = [first, second]
  existing_file = tmp_path / "first.png"
  existing_file.write_bytes(b"image")
  db = _db()

  monkeypatch.setattr(
    InfoRepository,
    "get_by_id",
    AsyncMock(return_value=info),
  )
  monkeypatch.setattr(
    InfoImageRepository,
    "get_images",
    AsyncMock(return_value=[first, second]),
  )
  delete = AsyncMock()
  monkeypatch.setattr(InfoImageRepository, "delete", delete)
  monkeypatch.setattr(
    "src.info.media.resolve_existing_info_image_path",
    lambda _key: existing_file,
  )

  await InfoImageService.delete_image(
    db,
    info.id,
    first.id,
    manager,
  )

  delete.assert_awaited_once_with(db, first)
  assert first.is_cover is False
  assert second.is_cover is True
  assert existing_file.exists()

  cleanup_commit_file_deletes(db)
  assert not existing_file.exists()
