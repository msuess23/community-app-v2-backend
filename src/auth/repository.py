import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import PasswordReset, RefreshSession


class AuthRepository:
  """Data access layer for the small amount of server-side auth state."""

  @staticmethod
  async def get_password_reset_by_user_id(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> Optional[PasswordReset]:
    result = await db.execute(
      select(PasswordReset).where(PasswordReset.user_id == user_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def save_password_reset(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    otp_hash: str,
    expires_at: datetime,
    requested_at: datetime,
  ) -> None:
    """Create or replace the one reset challenge belonging to a user."""
    reset = await AuthRepository.get_password_reset_by_user_id(db, user_id)
    if reset is None:
      db.add(
        PasswordReset(
          user_id=user_id,
          otp_hash=otp_hash,
          expires_at=expires_at,
          requested_at=requested_at,
        )
      )
      return

    reset.otp_hash = otp_hash
    reset.expires_at = expires_at
    reset.requested_at = requested_at

  @staticmethod
  async def delete_password_reset_by_id(
    db: AsyncSession,
    reset_id: uuid.UUID,
  ) -> None:
    await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_id))

  @staticmethod
  async def get_refresh_session_by_hash(
    db: AsyncSession,
    token_hash: str,
  ) -> Optional[RefreshSession]:
    result = await db.execute(
      select(RefreshSession).where(RefreshSession.token_hash == token_hash)
    )
    return result.scalar_one_or_none()

  @staticmethod
  def add_refresh_session(
    db: AsyncSession,
    session: RefreshSession,
  ) -> None:
    db.add(session)

  @staticmethod
  async def delete_refresh_session(
    db: AsyncSession,
    session_id: uuid.UUID,
  ) -> None:
    await db.execute(
      delete(RefreshSession).where(RefreshSession.id == session_id)
    )

  @staticmethod
  async def delete_all_refresh_sessions_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> None:
    await db.execute(
      delete(RefreshSession).where(RefreshSession.user_id == user_id)
    )
