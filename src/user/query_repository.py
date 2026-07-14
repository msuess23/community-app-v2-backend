from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.filters import apply_lifecycle_filter, apply_search_filter
from src.core.pagination import PaginationParams, SortOrder
from src.user.models import Role, User
from src.user.policies import UserReadScope
from src.user.schemas import UserSortField


class UserQueryRepository:
  """Read-model queries for authorized, paginated user collections."""

  @staticmethod
  async def get_page(
    db: AsyncSession,
    *,
    scope: UserReadScope,
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
    sort_expression = sort_column.asc() if order == SortOrder.ASC else sort_column.desc()
    id_tie_breaker = User.id.asc() if order == SortOrder.ASC else User.id.desc()

    query = (
      query.order_by(sort_expression, id_tie_breaker)
      .offset(pagination.offset)
      .limit(pagination.size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total
