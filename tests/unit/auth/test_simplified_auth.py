from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import uuid

import pytest

from src.auth.models import PasswordReset, RefreshSession
from src.auth.repository import AuthRepository
from src.auth.schemas import ResetPasswordRequest
from src.auth.service import AuthService
from src.core.security import hash_token
from src.user.models import Role, User
from src.user.repository import UserRepository


@pytest.mark.asyncio
async def test_password_reset_request_prints_demo_otp(monkeypatch, capsys) -> None:
  user = User(
    id=uuid.uuid4(),
    email="citizen@example.com",
    hashed_password="hash",
    first_name="Cora",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
  )
  monkeypatch.setattr(
    UserRepository,
    "get_by_email",
    AsyncMock(return_value=user),
  )
  save_reset = AsyncMock()
  monkeypatch.setattr(AuthRepository, "save_password_reset", save_reset)
  monkeypatch.setattr(
    "src.auth.service.get_password_hash",
    lambda value: f"hash:{value}",
  )

  await AuthService.request_password_reset(AsyncMock(), user.email)

  output = capsys.readouterr().out
  assert "[DEV] Password reset OTP" in output
  assert user.email in output
  otp = output.strip().rsplit(" ", maxsplit=1)[1]
  assert len(otp) == 6
  assert otp.isdigit()
  assert save_reset.await_args.kwargs["otp_hash"] == f"hash:{otp}"


@pytest.mark.asyncio
async def test_successful_password_reset_revokes_refresh_sessions(monkeypatch) -> None:
  user = User(
    id=uuid.uuid4(),
    email="citizen@example.com",
    hashed_password="old-hash",
    first_name="Cora",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
    auth_version=2,
  )
  reset = PasswordReset(
    id=uuid.uuid4(),
    user_id=user.id,
    otp_hash="otp-hash",
    expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
  )
  monkeypatch.setattr(
    UserRepository,
    "get_by_email",
    AsyncMock(return_value=user),
  )
  monkeypatch.setattr(
    AuthRepository,
    "get_password_reset_by_user_id",
    AsyncMock(return_value=reset),
  )
  delete_sessions = AsyncMock()
  delete_reset = AsyncMock()
  monkeypatch.setattr(
    AuthRepository,
    "delete_all_refresh_sessions_for_user",
    delete_sessions,
  )
  monkeypatch.setattr(
    AuthRepository,
    "delete_password_reset_by_id",
    delete_reset,
  )
  monkeypatch.setattr("src.auth.service.verify_password", lambda *_: True)
  monkeypatch.setattr(
    "src.auth.service.get_password_hash",
    lambda value: f"new:{value}",
  )

  db = AsyncMock()
  await AuthService.reset_password(
    db,
    ResetPasswordRequest(
      email=user.email,
      otp="123456",
      new_password="a-new-password",
    ),
  )

  assert user.hashed_password == "new:a-new-password"
  assert user.auth_version == 3
  delete_sessions.assert_awaited_once()
  delete_reset.assert_awaited_once_with(db, reset.id)


@pytest.mark.asyncio
async def test_refresh_rotation_replaces_only_presented_session(monkeypatch) -> None:
  user = User(
    id=uuid.uuid4(),
    email="citizen@example.com",
    hashed_password="hash",
    first_name="Cora",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
    auth_version=0,
  )
  old_token = "old-refresh-token"
  session = RefreshSession(
    id=uuid.uuid4(),
    user_id=user.id,
    token_hash=hash_token(old_token),
    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
  )
  db = AsyncMock()
  db.get.return_value = user
  monkeypatch.setattr(
    AuthRepository,
    "get_refresh_session_by_hash",
    AsyncMock(return_value=session),
  )
  delete_session = AsyncMock()
  monkeypatch.setattr(
    AuthRepository,
    "delete_refresh_session",
    delete_session,
  )
  added: list[RefreshSession] = []
  monkeypatch.setattr(
    AuthRepository,
    "add_refresh_session",
    lambda db, value: added.append(value),
  )
  monkeypatch.setattr(
    "src.auth.service.create_refresh_token",
    lambda: "new-refresh-token",
  )
  monkeypatch.setattr(
    "src.auth.service.create_access_token",
    lambda **kwargs: "access-token",
  )

  response = await AuthService.refresh_tokens(db, old_token)

  delete_session.assert_awaited_once_with(db, session.id)
  assert response.refresh_token == "new-refresh-token"
  assert response.access_token == "access-token"
  assert len(added) == 1
  assert added[0].token_hash == hash_token("new-refresh-token")
