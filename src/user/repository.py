import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update

from src.user.models import User, UserHistory, Role
from src.core.filters import LifecycleStatusFilter, apply_lifecycle_filter, apply_search_filter

class UserRepository:
  """
  Data access layer for User and UserHistory entities.
  Handles all direct database interactions, filtering, and bulk operations.
  """

  @staticmethod
  async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Fetches a user by email for authentication purposes."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Fetches a user by their UUID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_all(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 100,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None,
    exclude_citizens: bool = False,
    force_office_id: Optional[uuid.UUID] = None,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None
  ) -> List[User]:
    """
    Retrieves users with dynamic filtering.
    Applies security policies provided by the service layer (isolation and data minimization).
    """
    query = select(User)

    # Lifecycle filter
    query = apply_lifecycle_filter(query, User, status)

    # Text Search
    query = apply_search_filter(query, search, User.email, User.first_name, User.last_name)
    
    # Office & Role Filter
    if office_id:
      query = query.where(User.office_id == office_id)
    if role:
      query = query.where(User.role == role)
      
    # Filter out citizens
    if exclude_citizens:
      query = query.where(User.role != Role.CITIZEN)
      
    # Apply Tenant Isolation constraints
    if force_office_id:
      query = query.where(User.office_id == force_office_id)
      
    query = query.order_by(User.last_name).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

  @staticmethod
  def add(db: AsyncSession, user: User) -> None:
    """Stages a user entity for insertion or update."""
    db.add(user)

  @staticmethod
  def add_history(db: AsyncSession, history_entry: UserHistory) -> None:
    """Stages an audit trail entry for insertion."""
    db.add(history_entry)

  @staticmethod
  async def bulk_anonymize_history(
    db: AsyncSession, 
    target_roles: list[Role], 
    cutoff_date
  ) -> None:
    """
    Performs a bulk update on the UserHistory table to irreversibly anonymize 
    old audit records based on retention policies.
    """
    subquery = select(User.id).where(
      User.is_active == False,
      User.role.in_(target_roles),
      User.deactivated_at < cutoff_date
    )
    
    stmt = update(UserHistory).where(
      UserHistory.user_id.in_(subquery),
      UserHistory.email != "deleted@local.com"
    ).values(
      first_name="gelöschter",
      last_name="Nutzer",
      email="deleted@local.com"
    )
    await db.execute(stmt)


  @staticmethod
  async def get_history_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> List[UserHistory]:
    """Retrieves the audit trail for a specific user, newest first."""
    query = (
      select(UserHistory)
      .where(UserHistory.user_id == user_id)
      .order_by(UserHistory.changed_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()