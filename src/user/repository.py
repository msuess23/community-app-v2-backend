import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.filters import (
  LifecycleStatusFilter,
  SortOrder,
  apply_lifecycle_filter,
  apply_search_filter,
)
from src.core.pagination import execute_page
from src.user.models import Role, User, UserHistory, UserSortField


class UserRepository:
  """Data access layer for User and UserHistory entities."""

  SORT_COLUMNS = {
    UserSortField.CREATED_AT: User.created_at,
    UserSortField.EMAIL: User.email,
    UserSortField.FIRST_NAME: User.first_name,
    UserSortField.LAST_NAME: User.last_name,
    UserSortField.ROLE: User.role,
  }

  @staticmethod
  async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
    normalized_email = email.strip().lower()
    result = await db.execute(
      select(User).where(func.lower(User.email) == normalized_email)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_page(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None,
    exclude_citizens: bool = False,
    force_office_id: Optional[uuid.UUID] = None,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    sort_by: UserSortField = UserSortField.LAST_NAME,
    order: SortOrder = SortOrder.ASC,
  ) -> tuple[list[User], int]:
    query = select(User)
    query = apply_lifecycle_filter(query, User, status)
    query = apply_search_filter(
      query,
      search,
      User.email,
      User.first_name,
      User.last_name,
    )

    if office_id:
      query = query.where(User.office_id == office_id)
    if role:
      query = query.where(User.role == role)
    if exclude_citizens:
      query = query.where(User.role != Role.CITIZEN)
    if force_office_id:
      query = query.where(User.office_id == force_office_id)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=UserRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=User.id,
    )

  @staticmethod
  async def has_active_users_for_office(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> bool:
    result = await db.execute(
      select(User.id)
      .where(
        User.office_id == office_id,
        User.is_active.is_(True),
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None

  @staticmethod
  def add(db: AsyncSession, user: User) -> None:
    db.add(user)

  @staticmethod
  def add_history(db: AsyncSession, history_entry: UserHistory) -> None:
    db.add(history_entry)

  @staticmethod
  async def bulk_anonymize_citizen_history(
    db: AsyncSession,
    cutoff_date: datetime,
  ) -> None:
    """Anonymizes old snapshots of long-deactivated citizen accounts."""
    deactivated_citizens = select(User.id).where(
      User.is_active.is_(False),
      User.role == Role.CITIZEN,
      User.deactivated_at.is_not(None),
      User.deactivated_at < cutoff_date,
    )

    stmt = (
      update(UserHistory)
      .where(
        UserHistory.user_id.in_(deactivated_citizens),
        or_(
          UserHistory.email != "deleted@users.invalid",
          UserHistory.first_name != "gelöschter",
          UserHistory.last_name != "Nutzer",
        ),
      )
      .values(
        first_name="gelöschter",
        last_name="Nutzer",
        email="deleted@users.invalid",
      )
    )
    await db.execute(stmt)

  @staticmethod
  async def get_history_page(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    size: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> tuple[list[UserHistory], int]:
    query = select(UserHistory).where(UserHistory.user_id == user_id)

    if start_date:
      query = query.where(UserHistory.changed_at >= start_date)
    if end_date:
      query = query.where(UserHistory.changed_at <= end_date)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=UserHistory.changed_at,
      order=SortOrder.DESC,
      tie_breaker=UserHistory.id,
    )
