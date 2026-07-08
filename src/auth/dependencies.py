import uuid
import jwt
from fastapi import Depends, Path
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.user.models import User
from src.auth.models import BlacklistedToken
from src.core.exceptions import UnauthorizedException

# Define the OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.BASE_URL}/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
  """Validates JWT, checks against the blacklist, and returns the current user instance."""
  try:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    user_id_str = payload.get("sub")
    if not user_id_str:
      raise UnauthorizedException("Invalid token payload")

    user_id = uuid.UUID(user_id_str)
  except (jwt.PyJWTError, ValueError):
    raise UnauthorizedException("Could not validate credentials")

  # Check if the token has been revoked (logged out)
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
  """
  Role based guard
  Usage in routes: Depends(role_required(["ADMIN", "MANAGER"]))
  """
  async def guard(current_user: User = Depends(get_current_user)):
    if current_user.role not in allowed_roles:
      raise UnauthorizedException("Insufficient permissions")
    return current_user
  return guard

async def get_target_user_if_allowed(
  user_id: uuid.UUID = Path(...), 
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db)
) -> User:
  """
  Guard: Allows access only if the requested user_id matches the current_user's ID,
  or if the current_user is an ADMIN/MANAGER.
  Returns the target User object, ensuring IDOR protection.
  """
  # Case A: User is requesting their own data
  if current_user.id == user_id:
    return current_user
    
  # Case B: User is requesting someone else's data, but lacks permissions
  if current_user.role == "CITIZEN":
    raise UnauthorizedException("You do not have permission to access this resource.")
    
  # Case C: User is Admin/Manager. Load the target profile from the database.
  # Lazy import to avoid circular dependency issues during startup.
  from src.user.service import UserService 
  target_user = await UserService.get_user_by_id(db, user_id)
  
  return target_user