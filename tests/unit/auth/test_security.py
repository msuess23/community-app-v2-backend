import uuid

import pytest

from src.core.exceptions import UnauthorizedException
from src.core.security import (
  ACCESS_TOKEN_TYPE,
  create_access_token,
  decode_token,
  ensure_bcrypt_compatible,
  get_password_hash,
  hash_token,
  normalize_email,
  verify_password,
)


def test_access_token_requires_expected_type():
  token = create_access_token(uuid.uuid4())

  payload = decode_token(token, ACCESS_TOKEN_TYPE)

  assert payload["type"] == ACCESS_TOKEN_TYPE
  with pytest.raises(UnauthorizedException):
    decode_token(token, "refresh")


def test_malformed_password_hash_is_rejected_without_exception():
  assert verify_password("password123", "UNUSABLE_PASSWORD") is False


def test_password_hash_round_trip():
  hashed = get_password_hash("password123")
  assert verify_password("password123", hashed) is True
  assert verify_password("wrong-password", hashed) is False


def test_bcrypt_byte_limit_is_validated():
  with pytest.raises(ValueError):
    ensure_bcrypt_compatible("ä" * 37)


def test_email_and_token_hash_are_deterministic():
  assert normalize_email("  Citizen@Example.COM ") == "citizen@example.com"
  assert hash_token("token") == hash_token("token")
  assert hash_token("token") != hash_token("other-token")

@pytest.mark.asyncio
async def test_inactive_user_with_existing_access_token_is_rejected(monkeypatch):
  from unittest.mock import AsyncMock, MagicMock

  from src.auth.dependencies import get_current_user
  from src.user.models import Role, User
  from src.user.repository import UserRepository

  user = User(
    id=uuid.uuid4(),
    email="inactive@example.com",
    hashed_password="not-used",
    first_name="Inactive",
    last_name="User",
    role=Role.CITIZEN,
    is_active=False,
  )
  monkeypatch.setattr(
    UserRepository,
    "get_by_id",
    AsyncMock(return_value=user),
  )

  with pytest.raises(UnauthorizedException):
    await get_current_user(
      token=create_access_token(user.id),
      db=MagicMock(),
    )
