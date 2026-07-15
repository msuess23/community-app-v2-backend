import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ConflictException
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.office.service import OfficeService
from src.user.repository import UserRepository


def make_db() -> MagicMock:
  db = MagicMock()
  db.flush = AsyncMock()
  db.refresh = AsyncMock()
  return db


def make_office() -> Office:
  office = Office(
    id=uuid.uuid4(),
    name="Same Name",
    description="Old description",
    contact_email=None,
    phone=None,
    services=[],
    opening_hours={},
    is_active=True,
  )
  office.address = None
  return office


@pytest.mark.asyncio
async def test_duplicate_office_names_are_allowed(monkeypatch):
  db = make_db()
  monkeypatch.setattr(OfficeRepository, "add", MagicMock())

  result = await OfficeService.create_office(
    db,
    OfficeCreate(name="Same Name"),
    uuid.uuid4(),
  )

  assert result.name == "Same Name"
  assert db.flush.await_count == 2


@pytest.mark.asyncio
async def test_office_update_stores_resulting_state(monkeypatch):
  db = make_db()
  office = make_office()
  histories = []
  monkeypatch.setattr(
    OfficeRepository,
    "add_history",
    lambda _db, history: histories.append(history),
  )
  monkeypatch.setattr(OfficeRepository, "add", MagicMock())

  await OfficeService.update_office(
    db,
    office,
    OfficeUpdate(
      description="New description",
      change_reason="Responsibilities changed",
    ),
    uuid.uuid4(),
  )

  assert office.description == "New description"
  assert histories[0].description == "New description"
  assert histories[0].is_active is True
  assert histories[0].change_reason == "Responsibilities changed"


@pytest.mark.asyncio
async def test_office_with_active_users_cannot_be_deactivated(monkeypatch):
  office = make_office()
  monkeypatch.setattr(
    OfficeRepository,
    "get_by_id",
    AsyncMock(return_value=office),
  )
  monkeypatch.setattr(
    UserRepository,
    "has_active_users_for_office",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as error:
    await OfficeService.deactivate_office(
      make_db(),
      office.id,
      uuid.uuid4(),
      "Office merger",
    )

  assert error.value.error_code == "OFFICE_HAS_ACTIVE_USERS"
