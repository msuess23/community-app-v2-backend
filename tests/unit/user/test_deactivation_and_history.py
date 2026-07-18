import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.repository import AuthRepository
from src.core.exceptions import ConflictException, ForbiddenException
from src.ticket.services.lifecycle_guard import TicketLifecycleGuard
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.service import UserService


def make_db() -> MagicMock:
  db = MagicMock()
  db.flush = AsyncMock()
  return db


def make_user(role: Role) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{role.value.lower()}@example.com",
    hashed_password="not-used",
    first_name="Original",
    last_name="Person",
    role=role,
    office_id=uuid.uuid4() if role not in {Role.CITIZEN, Role.ADMIN} else None,
    is_active=True,
  )


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_own_account(monkeypatch):
  admin = make_user(Role.ADMIN)
  monkeypatch.setattr(
    UserRepository,
    "get_by_id",
    AsyncMock(return_value=admin),
  )

  with pytest.raises(ForbiddenException):
    await UserService.deactivate_user(
      make_db(),
      admin.id,
      admin.id,
      "Self deactivation",
    )


@pytest.mark.asyncio
async def test_citizen_deactivation_stores_final_anonymized_state(monkeypatch):
  db = make_db()
  citizen = make_user(Role.CITIZEN)
  histories = []
  monkeypatch.setattr(
    UserRepository,
    "get_by_id",
    AsyncMock(return_value=citizen),
  )
  monkeypatch.setattr(
    UserRepository,
    "add_history",
    lambda _db, history: histories.append(history),
  )
  monkeypatch.setattr(UserRepository, "add", MagicMock())
  monkeypatch.setattr(
    TicketLifecycleGuard,
    "ensure_user_is_not_required",
    AsyncMock(),
  )
  delete_sessions = AsyncMock()
  monkeypatch.setattr(
    AuthRepository,
    "delete_refresh_tokens_by_user_id",
    delete_sessions,
  )

  await UserService.deactivate_user(
    db,
    citizen.id,
    uuid.uuid4(),
    "Citizen requested account deletion",
  )

  assert histories[0].email == f"deleted+{citizen.id}@users.invalid"
  assert histories[0].is_active is False
  assert citizen.email == f"deleted+{citizen.id}@users.invalid"
  assert citizen.first_name == "gelöschter"
  assert citizen.last_name == "Nutzer"
  assert citizen.is_active is False
  assert citizen.deactivated_at is not None
  delete_sessions.assert_awaited_once_with(db, citizen.id)


@pytest.mark.asyncio
async def test_staff_deactivation_keeps_identity(monkeypatch):
  db = make_db()
  officer = make_user(Role.OFFICER)
  old_email = officer.email
  monkeypatch.setattr(
    UserRepository,
    "get_by_id",
    AsyncMock(return_value=officer),
  )
  monkeypatch.setattr(UserRepository, "add_history", MagicMock())
  monkeypatch.setattr(UserRepository, "add", MagicMock())
  monkeypatch.setattr(
    AuthRepository,
    "delete_refresh_tokens_by_user_id",
    AsyncMock(),
  )
  monkeypatch.setattr(
    TicketLifecycleGuard,
    "ensure_user_is_not_required",
    AsyncMock(),
  )

  await UserService.deactivate_user(
    db,
    officer.id,
    uuid.uuid4(),
    "Employment ended",
  )

  assert officer.email == old_email
  assert officer.first_name == "Original"
  assert officer.last_name == "Person"
  assert officer.is_active is False


@pytest.mark.asyncio
async def test_deep_anonymization_uses_only_citizen_history(monkeypatch):
  anonymize = AsyncMock()
  monkeypatch.setattr(
    UserRepository,
    "bulk_anonymize_citizen_history",
    anonymize,
  )

  db = make_db()
  await UserService.run_deep_anonymization(db)

  anonymize.assert_awaited_once()
  assert anonymize.await_args.args[0] is db


@pytest.mark.asyncio
async def test_user_with_active_ticket_cannot_be_deactivated(monkeypatch):
  citizen = make_user(Role.CITIZEN)
  monkeypatch.setattr(
    UserRepository,
    "get_by_id",
    AsyncMock(return_value=citizen),
  )
  guard = AsyncMock(
    side_effect=ConflictException(
      "User cannot be deactivated while referenced by an active ticket.",
      error_code="USER_HAS_ACTIVE_TICKETS",
    )
  )
  monkeypatch.setattr(
    TicketLifecycleGuard,
    "ensure_user_is_not_required",
    guard,
  )

  with pytest.raises(ConflictException) as error:
    await UserService.deactivate_user(
      make_db(),
      citizen.id,
      uuid.uuid4(),
      "Account deletion",
    )

  assert error.value.error_code == "USER_HAS_ACTIVE_TICKETS"
  assert citizen.is_active is True
