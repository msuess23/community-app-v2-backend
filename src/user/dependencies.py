import uuid

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.user.models import User
from src.user.policies import UserPolicy
from src.user.service import UserService


async def get_target_user_if_allowed(
  user_id: uuid.UUID = Path(...),
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db),
) -> User:
  """Load a user resource and enforce object-level read authorization."""
  target_user = await UserService.get_user_by_id(db, user_id)
  UserPolicy.require_can_read(current_user, target_user)
  return target_user
