import uuid

from fastapi import Depends, Path
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.security import ACCESS_TOKEN_TYPE, decode_token
from src.user.models import Role, User
from src.user.repository import UserRepository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.BASE_URL}/auth/login")


async def get_current_user(
  token: str = Depends(oauth2_scheme),
  db: AsyncSession = Depends(get_db),
) -> User:
  """Validates an access token and returns an active user."""
  payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)

  try:
    user_id = uuid.UUID(payload["sub"])
  except (KeyError, TypeError, ValueError) as exc:
    raise UnauthorizedException("Could not validate credentials") from exc

  user = await UserRepository.get_by_id(db, user_id)
  if user is None or not user.is_active:
    raise UnauthorizedException("Could not validate credentials")

  return user


def role_required(*allowed_roles: Role):
  """Dependency factory for endpoint-level role checks."""
  allowed = set(allowed_roles)

  async def guard(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in allowed:
      raise ForbiddenException()
    return current_user

  return guard


def can_access_user(current_user: User, target_user: User) -> bool:
  """Returns whether a user may read the target profile."""
  if current_user.id == target_user.id:
    return True

  if current_user.role == Role.ADMIN:
    return True

  if not target_user.is_active or target_user.role == Role.CITIZEN:
    return False

  if current_user.role == Role.DISPATCHER:
    return True

  if current_user.role in {Role.OFFICER, Role.MANAGER}:
    return (
      current_user.office_id is not None
      and current_user.office_id == target_user.office_id
    )

  return False


async def get_target_user_if_allowed(
  user_id: uuid.UUID = Path(...),
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db),
) -> User:
  target_user = await UserRepository.get_by_id(db, user_id)
  if target_user is None:
    raise ForbiddenException("You do not have permission to access this resource")

  if not can_access_user(current_user, target_user):
    raise ForbiddenException("You do not have permission to access this resource")

  return target_user
