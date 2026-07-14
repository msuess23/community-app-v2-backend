import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import (
  PasswordReset,
  RefreshSession,
  RefreshSessionRevokeReason,
)


class AuthRepository:
  """Data access layer for authentication-related entities."""

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
  async def upsert_password_reset(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    otp_hash: str,
    expires_at: datetime,
    requested_at: datetime,
    cooldown_before: datetime,
  ) -> bool:
    """
    Atomically create or replace a user's reset challenge.

    PostgreSQL evaluates the conflict-update predicate while holding the
    conflicting row lock. Parallel requests therefore cannot both bypass the
    per-account cooldown or create multiple active challenges.
    """
    statement = (
      insert(PasswordReset)
      .values(
        user_id=user_id,
        otp_hash=otp_hash,
        failed_attempts=0,
        expires_at=expires_at,
        requested_at=requested_at,
      )
      .on_conflict_do_update(
        constraint="uq_password_resets_user_id",
        set_={
          "otp_hash": otp_hash,
          "failed_attempts": 0,
          "expires_at": expires_at,
          "requested_at": requested_at,
        },
        where=PasswordReset.requested_at <= cooldown_before,
      )
      .returning(PasswordReset.id)
    )
    result = await db.execute(statement)
    return result.scalar_one_or_none() is not None

  @staticmethod
  async def get_password_reset_for_update(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> Optional[PasswordReset]:
    """Load and lock a reset challenge until the transaction finishes."""
    result = await db.execute(
      select(PasswordReset)
      .where(PasswordReset.user_id == user_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def delete_password_reset_by_id(
    db: AsyncSession,
    reset_id: uuid.UUID,
  ) -> None:
    await db.execute(
      delete(PasswordReset).where(PasswordReset.id == reset_id)
    )

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
