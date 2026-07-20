import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.dependencies import role_required
from src.auth.models import RefreshToken
from src.auth.repository import AuthRepository
from src.auth.service import AuthService
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.security import hash_token
from src.user.models import Role, User
from src.user.repository import UserRepository


def make_db() -> MagicMock:
  db = MagicMock()
  db.flush = AsyncMock()
  db.refresh = AsyncMock()
  db.commit = AsyncMock()
  db.rollback = AsyncMock()
  return db


def make_user(*, active: bool = True, role: Role = Role.CITIZEN) -> User:
  return User(
    id=uuid.uuid4(),
    email="citizen@example.com",
    hashed_password="not-used",
    first_name="Test",
    last_name="User",
    role=role,
    is_active=active,
  )


@pytest.mark.asyncio
async def test_inactive_user_cannot_log_in(monkeypatch):
  db = make_db()
  monkeypatch.setattr(
    UserRepository,
    "get_by_email",
    AsyncMock(return_value=make_user(active=False)),
  )

  with pytest.raises(UnauthorizedException):
    await AuthService.login(db, "citizen@example.com", "password123")


@pytest.mark.asyncio
async def test_refresh_rotates_the_stored_token_without_committing(monkeypatch):
  db = make_db()
  user = make_user()
  old_plain_token = "x" * 48
  stored = RefreshToken(
    id=uuid.uuid4(),
    user_id=user.id,
    token_hash=hash_token(old_plain_token),
    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
  )

  consume_refresh = AsyncMock(return_value=stored)
  add_refresh = MagicMock()
  monkeypatch.setattr(
    AuthRepository,
    "consume_refresh_token",
    consume_refresh,
  )
  monkeypatch.setattr(UserRepository, "get_by_id", AsyncMock(return_value=user))
  monkeypatch.setattr(AuthRepository, "add_refresh_token", add_refresh)

  response = await AuthService.refresh(db, old_plain_token)

  consume_refresh.assert_awaited_once_with(db, stored.token_hash)
  add_refresh.assert_called_once()
  db.flush.assert_awaited_once()
  db.commit.assert_not_awaited()
  assert response.refresh_token is not None
  assert response.refresh_token != old_plain_token


@pytest.mark.asyncio
async def test_unknown_refresh_token_is_rejected(monkeypatch):
  monkeypatch.setattr(
    AuthRepository,
    "consume_refresh_token",
    AsyncMock(return_value=None),
  )

  with pytest.raises(UnauthorizedException):
    await AuthService.refresh(make_db(), "x" * 48)


@pytest.mark.asyncio
async def test_logout_stages_refresh_token_deletion_without_committing(monkeypatch):
  db = make_db()
  delete_refresh = AsyncMock()
  monkeypatch.setattr(
    AuthRepository,
    "delete_refresh_token_by_hash",
    delete_refresh,
  )

  token = "x" * 48
  await AuthService.logout(db, token)

  delete_refresh.assert_awaited_once_with(db, hash_token(token))
  db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_role_guard_returns_forbidden_for_authenticated_user():
  officer = make_user(role=Role.OFFICER)
  guard = role_required(Role.ADMIN)

  with pytest.raises(ForbiddenException):
    await guard(current_user=officer)


@pytest.mark.asyncio
async def test_password_reset_replaces_password_and_invalidates_sessions(monkeypatch):
  from src.auth.models import PasswordReset
  from src.auth.schemas import ResetPasswordRequest
  from src.core.security import get_password_hash, verify_password

  db = make_db()
  user = make_user()
  reset_record = PasswordReset(
    id=uuid.uuid4(),
    email=user.email,
    otp_hash=get_password_hash("123456"),
    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
  )

  monkeypatch.setattr(
    AuthRepository,
    "get_password_reset_by_email",
    AsyncMock(return_value=reset_record),
  )
  monkeypatch.setattr(
    UserRepository,
    "get_by_email",
    AsyncMock(return_value=user),
  )
  delete_sessions = AsyncMock()
  delete_reset = AsyncMock()
  monkeypatch.setattr(
    AuthRepository,
    "delete_refresh_tokens_by_user_id",
    delete_sessions,
  )
  monkeypatch.setattr(
    AuthRepository,
    "delete_password_reset_by_id",
    delete_reset,
  )
  monkeypatch.setattr(UserRepository, "add", MagicMock())

  await AuthService.reset_password(
    db,
    ResetPasswordRequest(
      email=user.email,
      otp="123456",
      new_password="new-password-123",
    ),
  )

  AuthRepository.get_password_reset_by_email.assert_awaited_once_with(
    db,
    user.email,
    for_update=True,
  )
  assert verify_password("new-password-123", user.hashed_password)
  delete_sessions.assert_awaited_once_with(db, user.id)
  delete_reset.assert_awaited_once_with(db, reset_record.id)
  db.flush.assert_awaited_once()
  db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_reset_request_prints_development_otp(monkeypatch, capsys):
  db = make_db()
  user = make_user()
  monkeypatch.setattr(
    UserRepository,
    "get_by_email",
    AsyncMock(return_value=user),
  )
  monkeypatch.setattr(
    AuthRepository,
    "delete_password_resets_by_email",
    AsyncMock(),
  )
  add_reset = MagicMock()
  monkeypatch.setattr(AuthRepository, "add_password_reset", add_reset)

  await AuthService.request_password_reset(db, " Citizen@Example.COM ")

  output = capsys.readouterr().out
  assert "[DEV] Password reset OTP for citizen@example.com:" in output
  add_reset.assert_called_once()
  db.flush.assert_awaited_once()
  db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_all_invalidates_every_refresh_session(monkeypatch):
  db = make_db()
  user = make_user()
  delete_sessions = AsyncMock()
  monkeypatch.setattr(
    AuthRepository,
    "delete_refresh_tokens_by_user_id",
    delete_sessions,
  )

  await AuthService.logout_all(db, user.id)

  delete_sessions.assert_awaited_once_with(db, user.id)
  db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_auth_cleanup_uses_repository(monkeypatch):
  db = make_db()
  cleanup = AsyncMock(return_value=(4, 2))
  monkeypatch.setattr(AuthRepository, "delete_expired_records", cleanup)

  counts = await AuthService.cleanup_expired_records(db)

  assert counts == (4, 2)
  cleanup.assert_awaited_once()
  assert cleanup.await_args.kwargs["now"].tzinfo is not None
