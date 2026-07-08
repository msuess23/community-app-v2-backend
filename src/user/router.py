import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.auth.dependencies import get_current_user, role_required, get_target_user_if_allowed
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
  Updates the profile of the current user.
  Restricted to fields defined in UserUpdate schema.
  """
  return await UserService.update_user_profile(db, current_user, update_data, current_user.id)


@router.get("", response_model=List[UserResponse])
async def get_all_users(
  office_id: Optional[uuid.UUID] = None,
  role: Optional[Role] = None,
  skip: int = 0, 
  limit: int = 100,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN", "MANAGER", "DISPATCHER", "OFFICER"]))
):
  """
  Returns a list of all users.
  Supports filtering by office_id and role.
  Restricted to ADMIN, MANAGER, and DISPATCHER roles to support ticket assignment workflows.
  """
  return await UserService.get_all_users(db, skip, limit, office_id, role)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
  target_user: User = Depends(get_target_user_if_allowed)
):
  """
  Returns a specific user by ID.
  Access allowed for the user themselves, or by ADMIN/MANAGER.
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
  Strictly restricted to ADMIN role.
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
  Soft-deletes (deactivates) a user and triggers immediate partial anonymization.
  Strictly restricted to ADMIN role.
  """
  await UserService.deactivate_user(db, user_id, current_user.id)