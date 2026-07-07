from sqlalchemy.ext.asyncio import AsyncSession
from src.user.models import User, UserHistory
from src.user.schemas import UserUpdate
from src.core.exceptions import DomainException
import uuid

class UserService:
  """
  Handles business logic for user management, including audit trails.
  """
  
  @staticmethod
  async def update_user_profile(db: AsyncSession, user: User, update_data: UserUpdate) -> User:
    # 1. Extract only the fields that were actually provided in the request
    update_dict = update_data.model_dump(exclude_unset=True)
    
    if not update_dict:
      return user # No changes requested
      
    # 2. Apply updates to the user model
    for key, value in update_dict.items():
      setattr(user, key, value)
      
    # 3. Create an audit trail snapshot in UserHistory
    history_entry = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      changed_by_user_id=user.id,
      change_reason="User updated profile via API"
    )
    
    # 4. Save both the updated user and the history entry in one transaction
    db.add(user)
    db.add(history_entry)
    await db.commit()
    await db.refresh(user)
    
    return user

  @staticmethod
  async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
      raise DomainException("User not found", status_code=404)
    return user

  @staticmethod
  async def deactivate_user(db: AsyncSession, user_id: uuid.UUID, admin_id: uuid.UUID):
    user = await UserService.get_user_by_id(db, user_id)
    user.is_active = False
    
    # Historie schreiben
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