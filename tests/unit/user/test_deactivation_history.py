import uuid
from unittest.mock import AsyncMock

import pytest

from src.auth.repository import AuthRepository
from src.user.models import Role, User
from src.user.persistence import UserPersistence
from src.user.repository import UserRepository
from src.user.service import UserService


@pytest.mark.asyncio
async def test_deactivation_closes_identifiable_version_before_anonymization(monkeypatch) -> None:
  actor = User(id=uuid.uuid4(), role=Role.ADMIN, is_active=True)
  target = User(
    id=uuid.uuid4(),
    email="person@example.test",
    hashed_password="unused",
    first_name="Original",
    last_name="Person",
    role=Role.CITIZEN,
    office_id=None,
    is_active=True,
    auth_version=0,
  )
  state_when_closed: dict[str, object] = {}
  inserted_history = []

  async def close_current_history(db, user_id, *, valid_to):
    state_when_closed.update(
      email=target.email,
      first_name=target.first_name,
      is_active=target.is_active,
      valid_to=valid_to,
    )

  monkeypatch.setattr(
    UserService,
    "_get_locked_user",
    AsyncMock(return_value=target),
  )
  monkeypatch.setattr(
    UserPersistence,
    "close_current_history",
    close_current_history,
  )
  monkeypatch.setattr(
    UserRepository,
    "add_history",
    lambda db, history: inserted_history.append(history),
  )
  monkeypatch.setattr(
    AuthRepository,
    "revoke_all_refresh_sessions_for_user",
    AsyncMock(),
  )
  db = AsyncMock()

  await UserService.deactivate_user(
    db,
    target.id,
    actor,
    change_reason="Requested account deletion",
  )

  assert state_when_closed["email"] == "person@example.test"
  assert state_when_closed["first_name"] == "Original"
  assert state_when_closed["is_active"] is True

  new_version = inserted_history[0]
  assert new_version.email.startswith("deleted+")
  assert new_version.is_active is False
  assert new_version.valid_from == state_when_closed["valid_to"]
  assert new_version.change_reason == "Requested account deletion"
