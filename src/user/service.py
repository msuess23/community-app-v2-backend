import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.models import User, UserHistory
from src.user.schemas import UserUpdate
from src.core.exceptions import DomainException
from src.user.repository import UserRepository

class UserService:
  """
  Handles business logic for user management, including audit trails.
  Delegates database queries to the UserRepository.
  """
  
  @staticmethod
  async def update_user_profile(db: AsyncSession, user: User, update_data: UserUpdate) -> User:
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
      changed_by_user_id=user.id,
      change_reason="User updated profile via API"
    )
    
    # Delegate to repository for staging the changes
    UserRepository.add(db, user)
    UserRepository.add_history(db, history_entry)
    
    # Commit the transaction in the service layer
    await db.commit()
    await db.refresh(user)
    
    return user

  @staticmethod
  async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 100):
    return await UserRepository.get_all(db, skip, limit)

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await UserRepository.get_by_id(db, user_id)
    if not user:
      raise DomainException("User not found", status_code=404)
    return user

  @staticmethod
  async def deactivate_user(db: AsyncSession, user_id: uuid.UUID, admin_id: uuid.UUID):
    user = await UserService.get_user_by_id(db, user_id)
    
    if not user.is_active:
      raise DomainException("User is already deactivated", status_code=400)
      
    user.is_active = False
    
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