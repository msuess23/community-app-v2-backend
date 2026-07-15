import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.auth.repository import AuthRepository
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.service import UserService


@pytest.mark.asyncio
async def test_citizen_deactivation_archives_identity_before_anonymization(monkeypatch) -> None:
  actor = User(id=uuid.uuid4(), role=Role.ADMIN, is_active=True)
  version_start = datetime.now(timezone.utc) - timedelta(days=2)
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
    created_at=version_start,
    updated_at=version_start,
  )
  inserted_history = []

  monkeypatch.setattr(
    UserService,
    "_get_locked_user",
    AsyncMock(return_value=target),
  )
  monkeypatch.setattr(
    UserRepository,
    "add_history",
    lambda db, history: inserted_history.append(history),
  )
  monkeypatch.setattr(
    AuthRepository,
    "delete_all_refresh_sessions_for_user",
    AsyncMock(),
  )

  await UserService.deactivate_user(
    AsyncMock(),
    target.id,
    actor,
    change_reason="Requested account deletion",
  )

  archived = inserted_history[0]
  assert archived.email == "person@example.test"
  assert archived.first_name == "Original"
  assert archived.last_name == "Person"
  assert archived.is_active is True
  assert archived.valid_from == version_start
  assert archived.valid_to == target.updated_at
  assert archived.change_reason == "Requested account deletion"

  assert target.email.startswith("deleted+")
  assert target.first_name == "gelöschter"
  assert target.last_name == "Nutzer"
  assert target.is_active is False


@pytest.mark.asyncio
async def test_staff_deactivation_preserves_identity(monkeypatch) -> None:
  actor = User(id=uuid.uuid4(), role=Role.ADMIN, is_active=True)
  version_start = datetime.now(timezone.utc) - timedelta(days=1)
  target = User(
    id=uuid.uuid4(),
    email="officer@example.test",
    hashed_password="unused",
    first_name="Olivia",
    last_name="Officer",
    role=Role.OFFICER,
    office_id=uuid.uuid4(),
    is_active=True,
    auth_version=0,
    created_at=version_start,
    updated_at=version_start,
  )
  inserted_history = []

  monkeypatch.setattr(
    UserService,
    "_get_locked_user",
    AsyncMock(return_value=target),
  )
  monkeypatch.setattr(
    UserRepository,
    "add_history",
    lambda db, history: inserted_history.append(history),
  )
  monkeypatch.setattr(
    AuthRepository,
    "delete_all_refresh_sessions_for_user",
    AsyncMock(),
  )

  await UserService.deactivate_user(
    AsyncMock(),
    target.id,
    actor,
    change_reason="Employment ended",
  )

  assert target.email == "officer@example.test"
  assert target.first_name == "Olivia"
  assert target.last_name == "Officer"
  assert target.is_active is False
  assert inserted_history[0].email == "officer@example.test"
  assert inserted_history[0].is_active is True
