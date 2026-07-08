import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.user.models import User, UserHistory, Role
from src.user.schemas import UserUpdate
from src.core.exceptions import DomainException

class UserService:
  """
  Handles business logic for user management, including audit trails.
  """

  @staticmethod
  async def get_all_users(
    db: AsyncSession, 
    current_user: User,
    skip: int = 0, 
    limit: int = 100,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None
  ):
    """
    Retrieves users with optional filtering by office_id and role.
    Only ADMINs can list CITIZEN accounts in bulk.
    """
    query = select(User)
    
    if office_id:
      query = query.where(User.office_id == office_id)
    if role:
      query = query.where(User.role == role)

    if current_user.role != Role.ADMIN:
      query = query.where(User.role != Role.CITIZEN)

    if current_user.role == Role.OFFICER:
      query = query.where(User.office_id == current_user.office_id)
      
    # Order by last name for better UI presentation
    query = query.order_by(User.last_name).offset(skip).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
      raise DomainException("User not found", status_code=404)
    return user
  

  @staticmethod
  async def update_user_profile(
    db: AsyncSession, 
    user: User, 
    update_data: dict, 
    changed_by_user_id: uuid.UUID
  ) -> User:
    """
    Applies updates to a user profile and logs the change in the history table.
    Requires explicit passing of changed_by_user_id to differentiate between self-updates and admin-updates.
    """
    # Exclude unset fields from the update dictionary
    update_dict = update_data if isinstance(update_data, dict) else update_data.model_dump(exclude_unset=True)
    
    if not update_dict:
      return user 
      
    # Apply updates to the user model
    for key, value in update_dict.items():
      setattr(user, key, value)
      
    # Create an audit trail snapshot
    history_entry = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      changed_by_user_id=changed_by_user_id,
      change_reason="User profile updated via API"
    )
    
    db.add(user)
    db.add(history_entry)
    await db.commit()
    await db.refresh(user)
    
    return user


  @staticmethod
  async def deactivate_user(db: AsyncSession, user_id: uuid.UUID, admin_id: uuid.UUID):
    user = await UserService.get_user_by_id(db, user_id)

    # Immediate anonymization of live data (API protection)
    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.email = f"deleted@anonymized.local"
    user.first_name = "gelöschter"
    user.last_name = "Nutzer"
    user.hashed_password = "UNUSABLE_PASSWORD"
    
    # Anonymous history entry
    history_entry = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      changed_by_user_id=admin_id,
      change_reason="User deactivated by Administrator"
    )
    
    db.add(user)
    db.add(history_entry)
    await db.commit()


  @staticmethod
  async def run_deep_anonymization(db: AsyncSession):
    """
    Executes the second-tier anonymization process for audit data.
    Retention periods:
    - CITIZEN: 6 months (180 days)
    - OFFICER/MANAGER/ADMIN: 10 years (3650 days)
    """
    now = datetime.now(timezone.utc)
    cutoff_citizen = now - timedelta(days=180)
    cutoff_officer = now - timedelta(days=3650)
    
    async def anonymize_history_by_role(target_roles: list[Role], cutoff_date: datetime):
      """Helper function to perform bulk updates on the history table."""
      # Identify applicable user IDs
      subquery = select(User.id).where(
        User.is_active == False,
        User.role.in_(target_roles),
        User.deactivated_at < cutoff_date
      )
      
      # Execute bulk update on UserHistory if not already anonymized
      stmt = update(UserHistory).where(
        UserHistory.user_id.in_(subquery),
        UserHistory.email != "deleted@anonymized.local"
      ).values(
        first_name="gelöschter",
        last_name="Nutzer",
        email="deleted@anonymized.local"
      )
      
      await db.execute(stmt)

    # Process citizens
    await anonymize_history_by_role([Role.CITIZEN], cutoff_citizen)
    
    # Process authority personnel
    await anonymize_history_by_role([Role.OFFICER, Role.MANAGER, Role.ADMIN], cutoff_officer)
    
    await db.commit()
    print(f"[{now.isoformat()}] Cron task: Deep anonymization completed successfully.")