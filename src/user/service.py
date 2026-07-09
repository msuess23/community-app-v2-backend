import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Union

from src.user.models import User, UserHistory, Role
from src.user.schemas import UserUpdate, AdminUserUpdate
from src.core.exceptions import DomainException
from src.core.filters import LifecycleStatusFilter
from src.user.repository import UserRepository

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
      raise DomainException("Cannot update a deactivated user profile.", status_code=400)

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
    
    await db.commit()
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
    search: Optional[str] = None
  ):
    """
    Retrieves users while enforcing strict data minimization and isolation rules.
    """
    # Citizens should not be listed in bulk unless requested by an Admin
    exclude_citizens = current_user.role != Role.ADMIN
    
    # Officers are restricted to their own office namespace
    force_office_id = current_user.office_id if current_user.role == Role.OFFICER else None
    
    return await UserRepository.get_all(
      db, skip, limit, office_id, role, exclude_citizens, force_office_id, status, search
    )

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Retrieves a specific user and ensures existence."""
    user = await UserRepository.get_by_id(db, user_id)
    if not user:
      raise DomainException("User not found", status_code=404)
    return user

  @staticmethod
  async def deactivate_user(db: AsyncSession, user_id: uuid.UUID, admin_id: uuid.UUID):
    """
    Deactivates a user account and applies immediate Stage 1 anonymization 
    to protect live data exposure.
    """
    user = await UserService.get_user_by_id(db, user_id)
    
    if not user.is_active:
      raise DomainException("User is already deactivated", status_code=400)
      
    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.email = f"deleted@local.com"
    user.first_name = "gelöschter"
    user.last_name = "Nutzer"
    user.hashed_password = "UNUSABLE_PASSWORD"
    
    history_entry = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      changed_by_user_id=admin_id,
      change_reason="User deactivated by Administrator"
    )
    
    UserRepository.add(db, user)
    UserRepository.add_history(db, history_entry)
    await db.commit()

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
    await UserRepository.bulk_anonymize_history(db, [Role.OFFICER, Role.MANAGER, Role.ADMIN], cutoff_officer)
    
    await db.commit()
    print(f"[{now.isoformat()}] Cron task: Deep anonymization completed successfully.")


  @staticmethod
  async def get_user_history(db: AsyncSession, user_id: uuid.UUID) -> list[UserHistory]:
    """
    Retrieves the audit trail of a user profile.
    Ensures the user actually exists before returning history.
    """
    await UserService.get_user_by_id(db, user_id)
    return await UserRepository.get_history_by_user_id(db, user_id)