import uuid
from typing import Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.auth.models import PasswordReset, RefreshToken


class AuthRepository:
  """Data access for password-reset challenges and refresh tokens."""

  @staticmethod
  async def get_password_reset_by_email(
    db: AsyncSession,
    email: str,
  ) -> Optional[PasswordReset]:
    query = (
      select(PasswordReset)
      .where(PasswordReset.email == email)
      .order_by(PasswordReset.created_at.desc())
      .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()

  @staticmethod
  async def delete_password_resets_by_email(
    db: AsyncSession,
    email: str,
  ) -> None:
    await db.execute(delete(PasswordReset).where(PasswordReset.email == email))

  @staticmethod
  async def delete_password_reset_by_id(
    db: AsyncSession,
    reset_id: uuid.UUID,
  ) -> None:
    await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_id))

  @staticmethod
  def add_password_reset(db: AsyncSession, reset_record: PasswordReset) -> None:
    db.add(reset_record)

  @staticmethod
  async def get_refresh_token_by_hash(
    db: AsyncSession,
    token_hash: str,
  ) -> Optional[RefreshToken]:
    result = await db.execute(
      select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()

  @staticmethod
  def add_refresh_token(db: AsyncSession, token: RefreshToken) -> None:
    db.add(token)

  @staticmethod
  async def delete_refresh_token_by_hash(
    db: AsyncSession,
    token_hash: str,
  ) -> None:
    await db.execute(
      delete(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )

  @staticmethod
  async def delete_refresh_tokens_by_user_id(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> None:
    await db.execute(
      delete(RefreshToken).where(RefreshToken.user_id == user_id)
    )
