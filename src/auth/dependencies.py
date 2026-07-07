from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.user.models import User
from src.core.exceptions import UnauthorizedException

# Define the OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
  """Validates JWT and returns the current user."""
  try:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    user_id: str = payload.get("sub")
    if user_id is None:
      raise UnauthorizedException("Invalid token payload")
  except jwt.PyJWTError:
    raise UnauthorizedException("Could not validate credentials")

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