from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid

from src.core.database import get_db
from src.auth.dependencies import get_current_user, role_required, get_target_user_if_allowed
from src.user.models import User, Role
from src.user.schemas import UserResponse, UserUpdate, AdminUserUpdate
from src.user.service import UserService

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def get_my_profile(
  current_user: User = Depends(get_current_user)
):
  """Returns the profile of the currently authenticated user."""
  return current_user

@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
  update_data: UserUpdate,
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db)
):
  """Updates the profile of the current user."""
  return await UserService.update_user_profile(db, current_user, update_data, current_user.id)

@router.get("", response_model=List[UserResponse])
async def get_all_users(
  office_id: Optional[uuid.UUID] = None,
  role: Optional[Role] = None,
  include_inactive: bool = False,
  skip: int = 0, 
  limit: int = 100,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN", "MANAGER", "DISPATCHER", "OFFICER"]))
):
  """
  Returns a list of users.
  Enforces role-based isolation and data minimization under the hood.
  """
  return await UserService.get_all_users(db, current_user, skip, limit, office_id, role, include_inactive)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
  target_user: User = Depends(get_target_user_if_allowed)
):
  """
  Returns a specific user by ID.
  Guards against IDOR to protect citizen profiles.
  """
  return target_user

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_by_admin(
  user_id: uuid.UUID,
  update_data: AdminUserUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"]))
):
  """
  Updates a specific user's profile, including administrative fields like role and office_id.
  Strictly restricted to administrators.
  """
  target_user = await UserService.get_user_by_id(db, user_id)
  return await UserService.update_user_profile(db, target_user, update_data, current_user.id)

@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
  user_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"]))
):
  """
  Soft-deletes (deactivates) a user and scrubs their live data.
  """
  await UserService.deactivate_user(db, user_id, current_user.id)