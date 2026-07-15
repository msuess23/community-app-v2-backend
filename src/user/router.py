from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid
from datetime import datetime

from src.core.database import get_db
from src.auth.dependencies import get_current_user, role_required, get_target_user_if_allowed
from src.user.models import User, Role
from src.user.schemas import (
  AdminUserUpdate,
  UserDeactivateRequest,
  UserHistoryResponse,
  UserResponse,
  UserUpdate,
)
from src.user.service import UserService
from src.core.filters import LifecycleStatusFilter

router = APIRouter()

# --- Private Endpoints (current user) ---

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
  q: Optional[str] = Query(None, description="Search term for email, first name or last name"),
  office_id: Optional[uuid.UUID] = None,
  role: Optional[Role] = None,
  status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
  skip: int = 0, 
  limit: int = 100,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN, Role.MANAGER, Role.DISPATCHER, Role.OFFICER))
):
  """
  Returns a list of users.
  Enforces role-based isolation and data minimization under the hood.
  """
  return await UserService.get_all_users(db, current_user, skip, limit, office_id, role, status, q)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
  target_user: User = Depends(get_target_user_if_allowed)
):
  """
  Returns a specific user by ID.
  """
  return target_user


# --- Admin Endpoints ---

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_by_admin(
  user_id: uuid.UUID,
  update_data: AdminUserUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
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
  request: UserDeactivateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
):
  """
  Soft-deletes (deactivates) a user and scrubs their live data.
  """
  await UserService.deactivate_user(
    db,
    user_id,
    current_user.id,
    request.change_reason,
  )


@router.get("/{user_id}/history", response_model=List[UserHistoryResponse])
async def get_user_history(
  user_id: uuid.UUID,
  start_date: Optional[datetime] = Query(None, description="Start of the validity period"),
  end_date: Optional[datetime] = Query(None, description="End of the validity period"),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
):
  """
  Retrieves the audit trail/history for a specific user profile.
  Strictly restricted to administrators.
  """
  return await UserService.get_user_history(db, user_id, start_date, end_date)