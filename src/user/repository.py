import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.filters import apply_lifecycle_filter, apply_search_filter
from src.core.pagination import PaginationParams, SortOrder
from src.user.models import Role, User, UserHistory
from src.user.policies import UserListScope
from src.user.schemas import UserSortField


class UserRepository:
  """All user reads, writes, locks, and history queries in one place."""

  @staticmethod
  async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id_for_update(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> Optional[User]:
    result = await db.execute(
      select(User).where(User.id == user_id).with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_page(
    db: AsyncSession,
    *,
    scope: UserListScope,
    pagination: PaginationParams,
    search: Optional[str],
    sort_by: UserSortField,
    order: SortOrder,
  ) -> tuple[list[User], int]:
    query = select(User)
    query = apply_lifecycle_filter(query, User, scope.status)
    query = apply_search_filter(
      query,
      search,
      User.email,
      User.first_name,
      User.last_name,
    )

    if scope.office_id is not None:
      query = query.where(User.office_id == scope.office_id)
    if scope.role is not None:
      query = query.where(User.role == scope.role)
    if scope.exclude_citizens:
      query = query.where(User.role != Role.CITIZEN)

    total_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(total_query)).scalar_one())

    sort_columns = {
      UserSortField.LAST_NAME: User.last_name,
      UserSortField.FIRST_NAME: User.first_name,
      UserSortField.EMAIL: User.email,
      UserSortField.CREATED_AT: User.created_at,
    }
    sort_column = sort_columns[sort_by]
    direction = sort_column.asc if order == SortOrder.ASC else sort_column.desc
    id_direction = User.id.asc if order == SortOrder.ASC else User.id.desc

    result = await db.execute(
      query.order_by(direction(), id_direction())
      .offset(pagination.offset)
      .limit(pagination.size)
    )
    return list(result.scalars().all()), total

  @staticmethod
  async def has_active_users_in_office(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> bool:
    result = await db.execute(
      select(
        select(User.id)
        .where(User.office_id == office_id, User.is_active.is_(True))
        .exists()
      )
    )
    return bool(result.scalar())

  @staticmethod
  async def get_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> list[UserHistory]:
    query = select(UserHistory).where(UserHistory.user_id == user_id)
    if start_date is not None:
      query = query.where(UserHistory.valid_to > start_date)
    if end_date is not None:
      query = query.where(UserHistory.valid_from <= end_date)

    result = await db.execute(
      query.order_by(UserHistory.valid_from.desc(), UserHistory.id.desc())
    )
    return list(result.scalars().all())

  @staticmethod
  def add(db: AsyncSession, user: User) -> None:
    db.add(user)

  @staticmethod
  def add_history(db: AsyncSession, history_entry: UserHistory) -> None:
    db.add(history_entry)
