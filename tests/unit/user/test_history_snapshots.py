import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.auth.service import AuthService
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.schemas import UserCreate


@pytest.mark.asyncio
async def test_registration_creates_initial_result_state_snapshot(monkeypatch):
  db = MagicMock()
  db.flush = AsyncMock()
  db.refresh = AsyncMock()
  histories = []

  monkeypatch.setattr(UserRepository, "get_by_email", AsyncMock(return_value=None))
  monkeypatch.setattr(UserRepository, "add", MagicMock())
  monkeypatch.setattr(
    UserRepository,
    "add_history",
    lambda _db, history: histories.append(history),
  )

  user = await AuthService.register_user(
    db,
    UserCreate(
      email="citizen@example.com",
      password="password123",
      first_name="Test",
      last_name="Citizen",
    ),
  )

  assert user.role == Role.CITIZEN
  assert histories[0].user_id == user.id
  assert histories[0].is_active is True
  assert histories[0].change_reason == "USER_REGISTERED"
  assert histories[0].changed_by_user_id == user.id
