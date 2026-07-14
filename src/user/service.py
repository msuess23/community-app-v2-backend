import logging
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Union

from src.user.models import User, UserHistory, Role
from src.user.schemas import UserUpdate, AdminUserUpdate
from src.core.exceptions import (
  ConflictException,
  ResourceNotFoundException,
)
from src.core.filters import LifecycleStatusFilter
from src.core.security import create_unusable_password_hash
from src.auth.models import RefreshSessionRevokeReason
from src.auth.repository import AuthRepository
from src.user.policies import UserPolicy
from src.user.repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
  """
  Handles business logic for user management.
  Enforces permissions, data minimization, and coordinates the unit of work.
  """
  
  @staticmethod
  async def update_user_profile(
    db: AsyncSession, 
    user: User, 
    update_data: Union[UserUpdate, AdminUserUpdate], 
    changed_by_user_id: uuid.UUID
  ) -> User:
    """
    Applies updates to a user profile and logs the change in the history table.
    Accepts different update schemas based on the requester's role.
    """
    if getattr(user, "is_active", True) is False:
      raise ConflictException(
        "Cannot update a deactivated user profile.",
        error_code="USER_DEACTIVATED",
      )

    update_dict = update_data.model_dump(exclude_unset=True)
    
    if not update_dict:
      return user 
      
    for key, value in update_dict.items():
      setattr(user, key, value)
      
    history_entry = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      changed_by_user_id=changed_by_user_id,
      change_reason="User profile updated via API"
    )
    
    UserRepository.add(db, user)
    UserRepository.add_history(db, history_entry)
    
    await db.flush()
    return user

  @staticmethod
  async def update_user_by_admin(
    db: AsyncSession,
    *,
    actor: User,
    target_user: User,
    update_data: AdminUserUpdate,
  ) -> User:
    """Authorize and execute an administrative user update."""
    UserPolicy.require_can_admin_update(
      actor,
      target_user,
      new_role=update_data.role,
    )
    return await UserService.update_user_profile(
      db,
      target_user,
      update_data,
      actor.id,
    )

  @staticmethod
  async def get_all_users(
    db: AsyncSession, 
    current_user: User,
    skip: int = 0, 
    limit: int = 100,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None
  ):
    """
    Retrieves users while enforcing strict data minimization and isolation rules.
    """
    scope = UserPolicy.resolve_read_scope(
      current_user,
      requested_office_id=office_id,
      requested_role=role,
      requested_status=status,
    )

    return await UserRepository.get_all(
      db,
      scope,
      skip=skip,
      limit=limit,
      search=search,
    )

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Retrieves a specific user and ensures existence."""
    user = await UserRepository.get_by_id(db, user_id)
    if not user:
      raise ResourceNotFoundException(
        "User not found",
        error_code="USER_NOT_FOUND",
      )
    return user

  @staticmethod
  async def deactivate_user(db: AsyncSession, user_id: uuid.UUID, actor: User):
    """
    Deactivates a user account and applies immediate Stage 1 anonymization 
    to protect live data exposure.
    """
    user = await UserService.get_user_by_id(db, user_id)
    
    UserPolicy.require_can_deactivate(actor, user)

    if not user.is_active:
      raise ConflictException(
        "User is already deactivated",
        error_code="USER_ALREADY_DEACTIVATED",
      )
      
    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.email = f"deleted+{user.id}@users.invalid"
    user.first_name = "gelöschter"
    user.last_name = "Nutzer"
    user.hashed_password = create_unusable_password_hash()
    user.auth_version += 1
    
    history_entry = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      changed_by_user_id=actor.id,
      change_reason="User deactivated by Administrator"
    )
    
    UserRepository.add(db, user)
    UserRepository.add_history(db, history_entry)
    await AuthRepository.revoke_all_refresh_sessions_for_user(
      db,
      user.id,
      RefreshSessionRevokeReason.ACCOUNT_DEACTIVATED,
    )

  @staticmethod
  async def run_deep_anonymization(db: AsyncSession):
    """
    Cron job logic for Stage 2 anonymization. 
    Irreversibly scrubs PII from historical audit tables based on role retention policies.
    """
    now = datetime.now(timezone.utc)
    cutoff_citizen = now - timedelta(days=180)
    cutoff_officer = now - timedelta(days=3650)
    
    await UserRepository.bulk_anonymize_history(db, [Role.CITIZEN], cutoff_citizen)
    await UserRepository.bulk_anonymize_history(
      db,
      [Role.DISPATCHER, Role.OFFICER, Role.MANAGER, Role.ADMIN],
      cutoff_officer,
    )
    
    logger.info("Deep anonymization completed", extra={"completed_at": now.isoformat()})


  @staticmethod
  async def get_user_history(
    db: AsyncSession, 
    user_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
  ) -> list[UserHistory]:
    """
    Retrieves the audit trail of a user profile.
    Ensures the user actually exists before returning history.
    """
    await UserService.get_user_by_id(db, user_id)
    return await UserRepository.get_history_by_user_id(db, user_id, start_date, end_date)