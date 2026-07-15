import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.repository import AuthRepository
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ResourceNotFoundException,
)
from src.core.filters import LifecycleStatusFilter
from src.core.security import get_password_hash
from src.user.models import Role, User, UserHistory
from src.user.repository import UserRepository
from src.user.schemas import AdminUserUpdate, UserUpdate


class UserService:
  """Handles business logic for user management."""

  @staticmethod
  async def update_user_profile(
    db: AsyncSession,
    user: User,
    update_data: Union[UserUpdate, AdminUserUpdate],
    changed_by_user_id: uuid.UUID,
  ) -> User:
    if not user.is_active:
      raise DomainValidationException(
        "Cannot update a deactivated user profile.",
        error_code="USER_INACTIVE",
      )

    update_dict = update_data.model_dump(exclude_unset=True)
    if not update_dict:
      return user

    for key, value in update_dict.items():
      setattr(user, key, value)

    UserRepository.add_history(
      db,
      UserHistory(
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        changed_by_user_id=changed_by_user_id,
        change_reason="User profile updated via API",
      ),
    )
    UserRepository.add(db, user)

    await db.flush()
    await db.refresh(user)
    return user

  @staticmethod
  async def get_all_users(
    db: AsyncSession,
    current_user: User,
    skip: int = 0,
    limit: int = 100,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
  ):
    exclude_citizens = current_user.role != Role.ADMIN
    force_office_id = (
      current_user.office_id
      if current_user.role in {Role.OFFICER, Role.MANAGER}
      else None
    )
    effective_status = (
      status if current_user.role == Role.ADMIN else LifecycleStatusFilter.ACTIVE
    )

    return await UserRepository.get_all(
      db,
      skip,
      limit,
      office_id,
      role,
      exclude_citizens,
      force_office_id,
      effective_status,
      search,
    )

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await UserRepository.get_by_id(db, user_id)
    if user is None:
      raise ResourceNotFoundException(
        "User not found",
        error_code="USER_NOT_FOUND",
      )
    return user

  @staticmethod
  async def deactivate_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    admin_id: uuid.UUID,
  ) -> None:
    user = await UserService.get_user_by_id(db, user_id)

    if not user.is_active:
      raise ConflictException(
        "User is already deactivated",
        error_code="USER_ALREADY_DEACTIVATED",
      )

    UserRepository.add_history(
      db,
      UserHistory(
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        changed_by_user_id=admin_id,
        change_reason="User deactivated by Administrator",
      ),
    )

    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.hashed_password = get_password_hash(secrets.token_urlsafe(32))

    if user.role == Role.CITIZEN:
      user.email = f"deleted+{user.id}@users.invalid"
      user.first_name = "gelöschter"
      user.last_name = "Nutzer"

    UserRepository.add(db, user)
    await AuthRepository.delete_refresh_tokens_by_user_id(db, user.id)
    await db.flush()

  @staticmethod
  async def run_deep_anonymization(db: AsyncSession) -> None:
    """Stages the scheduled history anonymization in the caller's transaction."""
    now = datetime.now(timezone.utc)
    cutoff_citizen = now - timedelta(days=180)
    cutoff_officer = now - timedelta(days=3650)

    await UserRepository.bulk_anonymize_history(
      db,
      [Role.CITIZEN],
      cutoff_citizen,
    )
    await UserRepository.bulk_anonymize_history(
      db,
      [Role.OFFICER, Role.MANAGER, Role.DISPATCHER, Role.ADMIN],
      cutoff_officer,
    )

  @staticmethod
  async def get_user_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> list[UserHistory]:
    await UserService.get_user_by_id(db, user_id)
    return await UserRepository.get_history_by_user_id(
      db,
      user_id,
      start_date,
      end_date,
    )
