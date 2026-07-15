import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.filters import LifecycleStatusFilter
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.office.schemas import OfficeCreate
from src.office.service import OfficeService
from src.user.models import Role, User


def make_user(role: Role) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="unused",
    first_name="Test",
    last_name="User",
    role=role,
    is_active=True,
  )


@pytest.mark.asyncio
async def test_non_admin_office_list_forces_active_status(monkeypatch):
  get_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(OfficeRepository, "get_page", get_page)

  await OfficeService.get_all_offices(
    MagicMock(),
    current_user=make_user(Role.OFFICER),
    status=LifecycleStatusFilter.ALL,
  )

  assert get_page.await_args.kwargs["status"] == LifecycleStatusFilter.ACTIVE


@pytest.mark.asyncio
async def test_admin_office_list_honors_status(monkeypatch):
  get_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(OfficeRepository, "get_page", get_page)

  await OfficeService.get_all_offices(
    MagicMock(),
    current_user=make_user(Role.ADMIN),
    status=LifecycleStatusFilter.INACTIVE,
  )

  assert get_page.await_args.kwargs["status"] == LifecycleStatusFilter.INACTIVE


@pytest.mark.asyncio
async def test_office_create_adds_initial_snapshot(monkeypatch):
  db = MagicMock()
  db.flush = AsyncMock()
  db.refresh = AsyncMock()
  histories = []
  monkeypatch.setattr(OfficeRepository, "add", MagicMock())
  monkeypatch.setattr(
    OfficeRepository,
    "add_history",
    lambda _db, history: histories.append(history),
  )

  admin_id = uuid.uuid4()
  office = await OfficeService.create_office(
    db,
    OfficeCreate(name="Testamt"),
    admin_id,
  )

  assert histories[0].office_id == office.id
  assert histories[0].is_active is True
  assert histories[0].change_reason == "OFFICE_CREATED"
  assert histories[0].changed_by_user_id == admin_id


def test_address_has_no_office_back_reference():
  from src.address.models import Address

  assert not hasattr(Address, "office")
  assert not hasattr(Address, "offices")
