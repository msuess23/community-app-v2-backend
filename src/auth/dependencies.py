import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.exceptions import ForbiddenException, UnauthorizedException
from src.core.security import ACCESS_TOKEN_TYPE, decode_token
from src.user.models import Role, User
from src.user.repository import UserRepository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.BASE_URL}/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(
  tokenUrl=f"{settings.BASE_URL}/auth/login",
  auto_error=False,
)


async def get_current_user(
  token: str = Depends(oauth2_scheme),
  db: AsyncSession = Depends(get_db, scope="function"),
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


async def get_optional_current_user(
  token: str | None = Depends(optional_oauth2_scheme),
  db: AsyncSession = Depends(get_db, scope="function"),
) -> User | None:
  """Returns the authenticated active user or None for anonymous requests."""
  if token is None:
    return None
  return await get_current_user(token=token, db=db)


def role_required(*allowed_roles: Role):
  """Dependency factory for endpoint-level role checks."""
  allowed = set(allowed_roles)

  async def guard(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in allowed:
      raise ForbiddenException()
    return current_user

  return guard
