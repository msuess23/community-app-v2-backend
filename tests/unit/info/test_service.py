import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.address.models import Address
from src.core.exceptions import ForbiddenException
from src.info.image_service import InfoImageService
from src.info.models import Info, InfoCategory, InfoImage, InfoStatus, InfoStatusEntry
from src.info.repository import InfoRepository, InfoStatusRepository
from src.info.schemas import (
  InfoCreateRequest,
  InfoStatusCreateRequest,
  InfoUpdateRequest,
)
from src.info.service import InfoService
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.user.models import Role, User


def _db() -> MagicMock:
  db = MagicMock()
  db.flush = AsyncMock()
  return db


def _user(role: Role, *, office_id: uuid.UUID | None = None) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="hash",
    first_name="Info",
    last_name="Editor",
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _info(office_id: uuid.UUID | None) -> Info:
  now = datetime.now(timezone.utc)
  return Info(
    id=uuid.uuid4(),
    title="Road closure",
    description="Temporary closure",
    category=InfoCategory.CONSTRUCTION,
    office_id=office_id,
    current_status=InfoStatus.SCHEDULED,
    created_at=now,
    updated_at=now,
    starts_at=now + timedelta(days=1),
    ends_at=now + timedelta(days=2),
  )


def _status(info: Info, user: User) -> InfoStatusEntry:
  return InfoStatusEntry(
    id=uuid.uuid4(),
    info_id=info.id,
    status=info.current_status,
    message="Created",
    created_by_user_id=user.id,
    created_at=datetime.now(timezone.utc),
  )


@pytest.mark.asyncio
async def test_officer_can_create_only_for_own_active_office(monkeypatch) -> None:
  office_id = uuid.uuid4()
  officer = _user(Role.OFFICER, office_id=office_id)
  office = Office(
    id=office_id,
    name="Information Office",
    services=[],
    opening_hours={},
    is_active=True,
  )
  monkeypatch.setattr(OfficeRepository, "get_by_id", AsyncMock(return_value=office))
  staged_infos: list[Info] = []
  staged_statuses: list[InfoStatusEntry] = []
  monkeypatch.setattr(
    InfoRepository,
    "add",
    lambda _db, info: staged_infos.append(info),
  )
  monkeypatch.setattr(
    InfoStatusRepository,
    "add",
    lambda _db, entry: staged_statuses.append(entry),
  )
  monkeypatch.setattr(
    InfoService,
    "_response",
    staticmethod(lambda info, status: (info, status)),
  )
  starts_at = datetime.now(timezone.utc) + timedelta(days=1)

  info, status = await InfoService.create_info(
    _db(),
    InfoCreateRequest(
      title="Construction update",
      category=InfoCategory.CONSTRUCTION,
      office_id=office_id,
      starts_at=starts_at,
      ends_at=starts_at + timedelta(hours=2),
    ),
    officer,
  )

  assert staged_infos == [info]
  assert staged_statuses == [status]
  assert info.current_status == InfoStatus.SCHEDULED
  assert status.message == "Created"

  with pytest.raises(ForbiddenException):
    await InfoService.create_info(
      _db(),
      InfoCreateRequest(
        title="Wrong office",
        category=InfoCategory.OTHER,
        office_id=uuid.uuid4(),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
      ),
      officer,
    )


@pytest.mark.asyncio
async def test_case_worker_cannot_take_over_another_offices_info(monkeypatch) -> None:
  source_office_id = uuid.uuid4()
  target_office_id = uuid.uuid4()
  officer = _user(Role.OFFICER, office_id=target_office_id)
  info = _info(source_office_id)
  monkeypatch.setattr(
    InfoRepository,
    "get_by_id",
    AsyncMock(return_value=info),
  )

  with pytest.raises(ForbiddenException):
    await InfoService.update_info(
      _db(),
      info.id,
      InfoUpdateRequest(office_id=target_office_id),
      officer,
    )

  assert info.office_id == source_office_id


@pytest.mark.asyncio
async def test_admin_updates_same_row_and_can_remove_owned_address(monkeypatch) -> None:
  admin = _user(Role.ADMIN)
  info = _info(uuid.uuid4())
  info.address = Address(
    id=uuid.uuid4(),
    street="Main Street",
    house_number="1",
    zip_code="95028",
    city="Hof",
  )
  current = _status(info, admin)
  monkeypatch.setattr(
    InfoRepository,
    "get_by_id",
    AsyncMock(return_value=info),
  )
  monkeypatch.setattr(InfoRepository, "add", MagicMock())
  monkeypatch.setattr(
    InfoStatusRepository,
    "get_latest",
    AsyncMock(return_value=current),
  )
  monkeypatch.setattr(
    InfoService,
    "_response",
    staticmethod(lambda updated, status: (updated, status)),
  )
  original_id = info.id

  updated, returned_status = await InfoService.update_info(
    _db(),
    info.id,
    InfoUpdateRequest(
      title="Updated road closure",
      description=None,
      office_id=None,
      address=None,
    ),
    admin,
  )

  assert updated.id == original_id
  assert updated.title == "Updated road closure"
  assert updated.description is None
  assert updated.office_id is None
  assert updated.address is None
  assert returned_status is current


@pytest.mark.asyncio
async def test_delete_is_a_physical_repository_delete(monkeypatch) -> None:
  office_id = uuid.uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  info = _info(office_id)
  monkeypatch.setattr(
    InfoRepository,
    "get_by_id",
    AsyncMock(return_value=info),
  )
  image = InfoImage(
    id=uuid.uuid4(),
    info_id=info.id,
    storage_key=f"{info.id}/cover.png",
    original_filename="cover.png",
    mime_type="image/png",
    size_bytes=100,
    width=20,
    height=10,
    uploaded_by_user_id=manager.id,
    uploaded_at=datetime.now(timezone.utc),
    is_cover=True,
  )
  info.images = [image]
  delete = AsyncMock()
  register_files = MagicMock()
  monkeypatch.setattr(InfoRepository, "delete", delete)
  monkeypatch.setattr(
    InfoImageService,
    "register_file_deletions",
    register_files,
  )
  db = _db()

  await InfoService.delete_info(db, info.id, manager)

  register_files.assert_called_once_with(db, [image])
  delete.assert_awaited_once_with(db, info)
  db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_status_update_mutates_current_state_and_appends_history(monkeypatch) -> None:
  office_id = uuid.uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  info = _info(office_id)
  monkeypatch.setattr(
    InfoRepository,
    "get_by_id",
    AsyncMock(return_value=info),
  )
  staged: list[InfoStatusEntry] = []
  monkeypatch.setattr(
    InfoStatusRepository,
    "add",
    lambda _db, entry: staged.append(entry),
  )
  db = _db()

  response = await InfoService.add_status(
    db,
    info.id,
    InfoStatusCreateRequest(
      status=InfoStatus.ACTIVE,
      message="Work started",
    ),
    manager,
  )

  assert info.current_status == InfoStatus.ACTIVE
  assert response.status == InfoStatus.ACTIVE
  assert response.message == "Work started"
  assert staged[0].info_id == info.id


def test_info_response_exposes_current_cover_content_url() -> None:
  manager = _user(Role.MANAGER, office_id=uuid.uuid4())
  info = _info(manager.office_id)
  cover = InfoImage(
    id=uuid.uuid4(),
    info_id=info.id,
    storage_key=f"{info.id}/cover.png",
    original_filename="cover.png",
    mime_type="image/png",
    size_bytes=100,
    width=20,
    height=10,
    uploaded_by_user_id=manager.id,
    uploaded_at=datetime.now(timezone.utc),
    is_cover=True,
  )
  info.images = [cover]

  response = InfoService._response(info, _status(info, manager))

  assert response.image_url == (
    f"/api/v1/infos/{info.id}/images/{cover.id}/content"
  )
