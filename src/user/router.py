import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user, role_required
from src.core.database import get_db
from src.core.filters import LifecycleStatusFilter
from src.core.pagination import Page, PaginationParams, SortOrder
from src.user.dependencies import get_target_user_if_allowed
from src.user.models import Role, User
from src.user.schemas import (
  AdminUserCreate,
  AdminUserUpdate,
  UserDeactivate,
  UserHistoryResponse,
  UserResponse,
  UserSortField,
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


@router.get("", response_model=Page[UserResponse])
async def get_all_users(
  q: Optional[str] = Query(None, min_length=1, max_length=100),
  office_id: Optional[uuid.UUID] = None,
  role: Optional[Role] = None,
  status_filter: LifecycleStatusFilter = Query(
    LifecycleStatusFilter.ACTIVE,
    alias="status",
  ),
  sort_by: UserSortField = Query(UserSortField.LAST_NAME),
  order: SortOrder = Query(SortOrder.ASC),
  pagination: PaginationParams = Depends(),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(
    role_required(["ADMIN", "MANAGER", "DISPATCHER", "OFFICER"])
  ),
):
  return await UserService.get_all_users(
    db,
    current_user,
    pagination=pagination,
    office_id=office_id,
    role=role,
    status=status_filter,
    search=q,
    sort_by=sort_by,
    order=order,
  )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
  user_data: AdminUserCreate,
  db: AsyncSession = Depends(get_db),
  _current_user: User = Depends(role_required(["ADMIN"])),
):
  return await UserService.create_user_by_admin(
    db,
    user_data=user_data,
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
  current_user: User = Depends(role_required(["ADMIN"])),
):
  target_user = await UserService.get_user_by_id(db, user_id)
  return await UserService.update_user_by_admin(
    db,
    actor=current_user,
    target_user=target_user,
    update_data=update_data,
  )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
  user_id: uuid.UUID,
  command: UserDeactivate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])),
):
  await UserService.deactivate_user(
    db,
    user_id,
    current_user,
    change_reason=command.change_reason,
  )


@router.get("/{user_id}/history", response_model=list[UserHistoryResponse])
async def get_user_history(
  user_id: uuid.UUID,
  start_date: Optional[datetime] = Query(None),
  end_date: Optional[datetime] = Query(None),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])),
):
  return await UserService.get_user_history(
    db,
    user_id,
    start_date,
    end_date,
  )
