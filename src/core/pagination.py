"""Small shared SQLAlchemy helper for deterministic page queries."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.filters import SortOrder


T = TypeVar("T")


async def execute_page(
  db: AsyncSession,
  query: Select,
  *,
  page: int,
  size: int,
  sort_column: Any,
  order: SortOrder,
  tie_breaker: Any,
  unique: bool = False,
) -> tuple[list[T], int]:
  """Execute a count plus a stable page query without duplicating boilerplate."""

  count_query = select(func.count()).select_from(query.order_by(None).subquery())
  total = int((await db.execute(count_query)).scalar_one())

  ordering = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
  paged_query = (
    query.order_by(ordering, tie_breaker.asc())
    .offset((page - 1) * size)
    .limit(size)
  )
  scalars = (await db.execute(paged_query)).scalars()
  if unique:
    scalars = scalars.unique()
  return list(scalars.all()), total
