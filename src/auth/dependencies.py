from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.core.config import settings
from src.core.database import get_db
from src.user.models import User
from src.core.exceptions import UnauthorizedException
from src.auth.models import BlacklistedToken

# Define the OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.BASE_URL}/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
  """Validates JWT and returns the current user."""
  try:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    user_id_str = payload.get("sub")
    if not user_id_str:
      raise UnauthorizedException("Invalid token payload")

    user_id = uuid.UUID(user_id_str)
  except (jwt.PyJWTError, ValueError):
    raise UnauthorizedException("Could not validate credentials")

  is_blacklisted = await db.execute(select(BlacklistedToken).where(BlacklistedToken.token == token))
  if is_blacklisted.scalar_one_or_none():
    raise UnauthorizedException("Token has been revoked. Please log in again.")

  result = await db.execute(select(User).where(User.id == user_id))
  user = result.scalar_one_or_none()
  
  if user is None:
    raise UnauthorizedException("User not found")
  return user

# Role-based guards (Dependency Factories)
def role_required(allowed_roles: list[str]):
  async def guard(current_user: User = Depends(get_current_user)):
    if current_user.role not in allowed_roles:
      raise UnauthorizedException("Insufficient permissions")
    return current_user
  return guard

# Usage in routes: Depends(role_required(["ADMIN", "MANAGER"]))