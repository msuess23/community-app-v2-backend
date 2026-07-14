import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from datetime import datetime

from src.user.models import User, UserHistory, Role
from src.core.filters import apply_lifecycle_filter, apply_search_filter
from src.user.policies import UserReadScope

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
  async def get_by_email_for_update(
    db: AsyncSession,
    email: str,
  ) -> Optional[User]:
    """Fetch and lock a user for a security-sensitive mutation."""
    result = await db.execute(
      select(User)
      .where(User.email == email)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """Fetches a user by their UUID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_all(
    db: AsyncSession,
    scope: UserReadScope,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None
  ) -> List[User]:
    """Retrieve users inside an already-authorized visibility scope."""
    query = select(User)
    query = apply_lifecycle_filter(query, User, scope.status)
    query = apply_search_filter(query, search, User.email, User.first_name, User.last_name)

    if scope.office_id is not None:
      query = query.where(User.office_id == scope.office_id)
    if scope.role is not None:
      query = query.where(User.role == scope.role)
    if scope.exclude_citizens:
      query = query.where(User.role != Role.CITIZEN)

    query = query.order_by(User.last_name, User.first_name, User.id).offset(skip).limit(limit)
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
    async def get_history_by_user_id(
    db: AsyncSession, 
    user_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
    ) -> List[UserHistory]:
      """Retrieves the audit trail for a specific user, newest first."""
      records = []

      # Get last change that was made before the start_date as 
      # it would still be active during part of the time frame
      if start_date:
        query_before = (
          select(UserHistory)
          .where(UserHistory.user_id == user_id, UserHistory.changed_at < start_date)
          .order_by(UserHistory.changed_at.desc())
          .limit(1)
        )
        result_before = await db.execute(query_before)
        before_record = result_before.scalar_one_or_none()
        if before_record:
          records.append(before_record)

      # Get all changes within the time frame
      query_range = select(UserHistory).where(UserHistory.user_id == user_id)

      if start_date:
        query_range = query_range.where(UserHistory.changed_at >= start_date)
      if end_date:
        query_range = query_range.where(UserHistory.changed_at <= end_date)

      query_range = query_range.order_by(UserHistory.changed_at.desc())

      result_range = await db.execute(query_range)
      range_records = list(result_range.scalars().all())

      # Combine both
      return range_records + records