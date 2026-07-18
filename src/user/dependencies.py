"""FastAPI dependencies for object-level user authorization."""

import uuid

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.exceptions import ForbiddenException
from src.user.access_policy import UserAccessPolicy
from src.user.models import User
from src.user.repository import UserRepository


async def get_target_user_if_allowed(
  user_id: uuid.UUID = Path(...),
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db),
) -> User:
  """Load a target user while hiding inaccessible profiles as forbidden."""

  target_user = await UserRepository.get_by_id(db, user_id)
  if target_user is None or not UserAccessPolicy.can_access(current_user, target_user):
    raise ForbiddenException("You do not have permission to access this resource")
  return target_user
