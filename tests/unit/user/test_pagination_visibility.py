import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.filters import LifecycleStatusFilter
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.service import UserService


def make_user(role: Role, office_id=None) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="unused",
    first_name="Test",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=True,
  )


@pytest.mark.asyncio
async def test_non_admin_user_list_forces_active_status(monkeypatch):
  get_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(UserRepository, "get_page", get_page)

  await UserService.get_all_users(
    MagicMock(),
    make_user(Role.DISPATCHER),
    status=LifecycleStatusFilter.ALL,
  )

  assert get_page.await_args.kwargs["status"] == LifecycleStatusFilter.ACTIVE


@pytest.mark.asyncio
async def test_admin_user_list_honors_inactive_status(monkeypatch):
  get_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(UserRepository, "get_page", get_page)

  response = await UserService.get_all_users(
    MagicMock(),
    make_user(Role.ADMIN),
    page=2,
    size=5,
    status=LifecycleStatusFilter.INACTIVE,
  )

  assert get_page.await_args.kwargs["status"] == LifecycleStatusFilter.INACTIVE
  assert response.page == 2
  assert response.size == 5
  assert response.pages == 0
