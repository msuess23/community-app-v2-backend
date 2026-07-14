import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.models import User, UserHistory


class UserPersistence:
  """Locking and temporal-history operations kept separate from the legacy repository.

  This module intentionally avoids changing ``src/user/repository.py`` so the
  temporal-history migration can be applied on top of projects where the prior
  indentation fix was implemented with slightly different source formatting.
  """

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
  async def close_current_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    valid_to: datetime,
  ) -> None:
    await db.execute(
      update(UserHistory)
      .where(
        UserHistory.user_id == user_id,
        UserHistory.valid_to.is_(None),
      )
      .values(valid_to=valid_to)
    )

  @staticmethod
  async def get_history_by_user_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> list[UserHistory]:
    """Return versions whose validity interval overlaps the requested range."""
    query = select(UserHistory).where(UserHistory.user_id == user_id)

    if start_date is not None:
      query = query.where(
        UserHistory.valid_to.is_(None) | (UserHistory.valid_to > start_date)
      )
    if end_date is not None:
      query = query.where(UserHistory.valid_from <= end_date)

    query = query.order_by(UserHistory.valid_from.desc(), UserHistory.id.desc())
    result = await db.execute(query)
    return list(result.scalars().all())
