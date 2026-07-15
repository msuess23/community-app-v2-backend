import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.core.exceptions import (
  DomainValidationException,
  ForbiddenException,
)
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.schemas import AdminUserUpdate, UserCreate
from src.user.service import UserService


def make_db() -> MagicMock:
  db = MagicMock()
  db.flush = AsyncMock()
  db.refresh = AsyncMock()
  return db


def make_user(
  role: Role,
  *,
  office_id: uuid.UUID | None = None,
  active: bool = True,
) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="not-used",
    first_name="Old",
    last_name="Name",
    role=role,
    office_id=office_id,
    is_active=active,
  )


def make_office(*, active: bool = True) -> Office:
  return Office(
    id=uuid.uuid4(),
    name="Example Office",
    is_active=active,
    services=[],
    opening_hours={},
  )


def test_registration_schema_rejects_role_and_office_injection():
  with pytest.raises(ValidationError):
    UserCreate(
      email="citizen@example.com",
      password="password123",
      first_name="Test",
      last_name="Citizen",
      role=Role.ADMIN,
      office_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_admin_can_promote_citizen_to_officer_with_active_office(monkeypatch):
  db = make_db()
  admin_id = uuid.uuid4()
  citizen = make_user(Role.CITIZEN)
  office = make_office()
  histories = []

  monkeypatch.setattr(
    OfficeRepository,
    "get_by_id",
    AsyncMock(return_value=office),
  )
  monkeypatch.setattr(
    UserRepository,
    "add_history",
    lambda _db, history: histories.append(history),
  )
  monkeypatch.setattr(UserRepository, "add", MagicMock())

  result = await UserService.update_user_profile(
    db,
    citizen,
    AdminUserUpdate(
      role=Role.OFFICER,
      office_id=office.id,
      change_reason="Employment as case officer",
    ),
    admin_id,
  )

  assert result.role == Role.OFFICER
  assert result.office_id == office.id
  assert len(histories) == 1
  assert histories[0].role == Role.CITIZEN
  assert histories[0].office_id is None
  assert histories[0].change_reason == "Employment as case officer"


@pytest.mark.asyncio
async def test_officer_role_requires_office(monkeypatch):
  citizen = make_user(Role.CITIZEN)

  with pytest.raises(DomainValidationException) as error:
    await UserService.update_user_profile(
      make_db(),
      citizen,
      AdminUserUpdate(
        role=Role.OFFICER,
        change_reason="Employment as case officer",
      ),
      uuid.uuid4(),
    )

  assert error.value.error_code == "OFFICE_REQUIRED_FOR_ROLE"


@pytest.mark.asyncio
async def test_staff_account_cannot_be_changed_back_to_citizen():
  officer = make_user(Role.OFFICER, office_id=uuid.uuid4())

  with pytest.raises(DomainValidationException) as error:
    await UserService.update_user_profile(
      make_db(),
      officer,
      AdminUserUpdate(
        role=Role.CITIZEN,
        change_reason="Invalid downgrade",
      ),
      uuid.uuid4(),
    )

  assert error.value.error_code == "STAFF_TO_CITIZEN_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_admin_cannot_degrade_own_role():
  admin = make_user(Role.ADMIN)

  with pytest.raises(ForbiddenException):
    await UserService.update_user_profile(
      make_db(),
      admin,
      AdminUserUpdate(
        role=Role.OFFICER,
        office_id=uuid.uuid4(),
        change_reason="Self downgrade",
      ),
      admin.id,
    )


@pytest.mark.asyncio
async def test_switching_to_admin_clears_office(monkeypatch):
  office_id = uuid.uuid4()
  manager = make_user(Role.MANAGER, office_id=office_id)
  monkeypatch.setattr(UserRepository, "add_history", MagicMock())
  monkeypatch.setattr(UserRepository, "add", MagicMock())

  await UserService.update_user_profile(
    make_db(),
    manager,
    AdminUserUpdate(
      role=Role.ADMIN,
      office_id=office_id,
      change_reason="Appointment as administrator",
    ),
    uuid.uuid4(),
  )

  assert manager.role == Role.ADMIN
  assert manager.office_id is None


@pytest.mark.asyncio
async def test_inactive_office_cannot_be_assigned(monkeypatch):
  citizen = make_user(Role.CITIZEN)
  office = make_office(active=False)
  monkeypatch.setattr(
    OfficeRepository,
    "get_by_id",
    AsyncMock(return_value=office),
  )

  with pytest.raises(DomainValidationException) as error:
    await UserService.update_user_profile(
      make_db(),
      citizen,
      AdminUserUpdate(
        role=Role.MANAGER,
        office_id=office.id,
        change_reason="Manager assignment",
      ),
      uuid.uuid4(),
    )

  assert error.value.error_code == "OFFICE_INACTIVE"
