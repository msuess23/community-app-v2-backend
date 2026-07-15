from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import (
  get_current_user,
  get_target_user_if_allowed,
  role_required,
)
from src.core.database import get_db
from src.core.filters import LifecycleStatusFilter, SortOrder
from src.core.schemas import PaginatedResponse
from src.user.models import Role, User, UserSortField
from src.user.schemas import (
  AdminUserUpdate,
  UserDeactivateRequest,
  UserHistoryResponse,
  UserResponse,
  UserUpdate,
)
from src.user.service import UserService


router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
  current_user: User = Depends(get_current_user),
):
  return current_user


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
  update_data: UserUpdate,
  current_user: User = Depends(get_current_user),
  db: AsyncSession = Depends(get_db),
):
  return await UserService.update_user_profile(
    db,
    current_user,
    update_data,
    current_user.id,
  )


@router.get("", response_model=PaginatedResponse[UserResponse])
async def get_all_users(
  q: Optional[str] = Query(
    None,
    max_length=200,
    description="Search term for email, first name or last name",
  ),
  office_id: Optional[uuid.UUID] = None,
  role: Optional[Role] = None,
  status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
  page: int = Query(1, ge=1),
  size: int = Query(20, ge=1, le=100),
  sort_by: UserSortField = UserSortField.LAST_NAME,
  order: SortOrder = SortOrder.ASC,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(Role.ADMIN, Role.MANAGER, Role.DISPATCHER, Role.OFFICER)
  ),
):
  """Lists users with role-based visibility and admin-only lifecycle filtering."""
  return await UserService.get_all_users(
    db,
    current_user,
    page=page,
    size=size,
    office_id=office_id,
    role=role,
    status=status,
    search=q,
    sort_by=sort_by,
    order=order,
  )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
  target_user: User = Depends(get_target_user_if_allowed),
):
  return target_user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user_by_admin(
  user_id: uuid.UUID,
  update_data: AdminUserUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN)),
):
  target_user = await UserService.get_user_by_id(db, user_id)
  return await UserService.update_user_profile(
    db,
    target_user,
    update_data,
    current_user.id,
  )


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
  user_id: uuid.UUID,
  request: UserDeactivateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN)),
):
  await UserService.deactivate_user(
    db,
    user_id,
    current_user.id,
    request.change_reason,
  )


@router.get("/{user_id}/history", response_model=list[UserHistoryResponse])
async def get_user_history(
  user_id: uuid.UUID,
  start_date: Optional[datetime] = Query(None),
  end_date: Optional[datetime] = Query(None),
  db: AsyncSession = Depends(get_db),
  _current_user: User = Depends(role_required(Role.ADMIN)),
):
  return await UserService.get_user_history(db, user_id, start_date, end_date)
