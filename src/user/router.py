from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from src.core.database import get_db
from src.auth.dependencies import get_current_user, role_required
from src.user.models import User
from src.user.schemas import UserResponse, UserUpdate
from src.user.service import UserService

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def get_my_profile(
  current_user: User = Depends(get_current_user)
):
  """
  Returns the profile of the currently authenticated user.
  Requires a valid JWT Access Token.
  """
  return current_user

@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
  update_data: UserUpdate,
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db)
):
  """
  Updates the profile of the current user and creates an audit trail entry.
  """
  return await UserService.update_user_profile(db, current_user, update_data)

@router.get("", response_model=List[UserResponse])
async def get_all_users(
  skip: int = 0, 
  limit: int = 100,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN", "MANAGER"])) # Nur Admins/Manager!
):
  """Returns a list of all users."""
  return await UserService.get_all_users(db, skip, limit)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
  user_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN", "MANAGER"]))
):
  """Returns a specific user by ID."""
  return await UserService.get_user_by_id(db, user_id)

@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
  user_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])) # Nur echte Admins dürfen deaktiveren
):
  """Soft-deletes (deactivates) a user."""
  await UserService.deactivate_user(db, user_id, current_user.id)