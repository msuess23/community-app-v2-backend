import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import ResourceNotFoundException
from src.user.repository import UserRepository
from src.user.service import UserService


@pytest.mark.asyncio
async def test_missing_user_has_stable_error_code(monkeypatch):
  monkeypatch.setattr(
    UserRepository,
    "get_by_id",
    AsyncMock(return_value=None),
  )

  with pytest.raises(ResourceNotFoundException) as error:
    await UserService.get_user_by_id(MagicMock(), uuid.uuid4())

  assert error.value.error_code == "USER_NOT_FOUND"
  assert error.value.status_code == 404
