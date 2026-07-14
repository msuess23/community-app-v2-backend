import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import (
  PasswordReset,
  RefreshSession,
  RefreshSessionRevokeReason,
)


class AuthRepository:
  """Data access layer for authentication-related entities."""

  @staticmethod
  async def get_password_reset_by_email(
    db: AsyncSession,
    email: str,
  ) -> Optional[PasswordReset]:
    result = await db.execute(
      select(PasswordReset).where(PasswordReset.email == email)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def delete_password_resets_by_email(
    db: AsyncSession,
    email: str,
  ) -> None:
    await db.execute(
      delete(PasswordReset).where(PasswordReset.email == email)
    )

  @staticmethod
  async def delete_password_reset_by_id(
    db: AsyncSession,
    reset_id: uuid.UUID,
  ) -> None:
    await db.execute(
      delete(PasswordReset).where(PasswordReset.id == reset_id)
    )

  @staticmethod
  def add_password_reset(
    db: AsyncSession,
    reset_record: PasswordReset,
  ) -> None:
    db.add(reset_record)

  @staticmethod
  async def get_refresh_session_for_update(
    db: AsyncSession,
    session_id: uuid.UUID,
  ) -> Optional[RefreshSession]:
    """
    Load and lock a refresh-session row until the current transaction ends.

    The row lock serializes concurrent attempts to rotate the same token, so
    exactly one request can succeed. A later request observes the token as
    already rotated and triggers replay handling.
    """
    result = await db.execute(
      select(RefreshSession)
      .where(RefreshSession.id == session_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  def add_refresh_session(
    db: AsyncSession,
    session: RefreshSession,
  ) -> None:
    db.add(session)

  @staticmethod
  async def revoke_refresh_session_family(
    db: AsyncSession,
    family_id: uuid.UUID,
    reason: RefreshSessionRevokeReason,
    *,
    revoked_at: datetime | None = None,
  ) -> int:
    timestamp = revoked_at or datetime.now(timezone.utc)
    result = await db.execute(
      update(RefreshSession)
      .where(
        RefreshSession.family_id == family_id,
        RefreshSession.revoked_at.is_(None),
      )
      .values(
        revoked_at=timestamp,
        revoke_reason=reason.value,
      )
    )
    return result.rowcount or 0

  @staticmethod
  async def revoke_all_refresh_sessions_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    reason: RefreshSessionRevokeReason,
    *,
    revoked_at: datetime | None = None,
  ) -> int:
    timestamp = revoked_at or datetime.now(timezone.utc)
    result = await db.execute(
      update(RefreshSession)
      .where(
        RefreshSession.user_id == user_id,
        RefreshSession.revoked_at.is_(None),
      )
      .values(
        revoked_at=timestamp,
        revoke_reason=reason.value,
      )
    )
    return result.rowcount or 0
