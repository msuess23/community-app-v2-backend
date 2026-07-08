import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from src.auth.models import PasswordReset, BlacklistedToken

class AuthRepository:
  """
  Data access layer for authentication-related entities (Tokens, Password Resets).
  """

  @staticmethod
  async def get_password_reset_by_email(db: AsyncSession, email: str) -> Optional[PasswordReset]:
    result = await db.execute(select(PasswordReset).where(PasswordReset.email == email))
    return result.scalar_one_or_none()

  @staticmethod
  async def delete_password_resets_by_email(db: AsyncSession, email: str) -> None:
    await db.execute(delete(PasswordReset).where(PasswordReset.email == email))

  @staticmethod
  async def delete_password_reset_by_id(db: AsyncSession, reset_id: uuid.UUID) -> None:
    await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_id))

  @staticmethod
  def add_password_reset(db: AsyncSession, reset_record: PasswordReset) -> None:
    db.add(reset_record)

  @staticmethod
  async def is_token_blacklisted(db: AsyncSession, token: str) -> bool:
    result = await db.execute(select(BlacklistedToken).where(BlacklistedToken.token == token))
    return result.scalar_one_or_none() is not None

  @staticmethod
  def add_blacklisted_token(db: AsyncSession, token_record: BlacklistedToken) -> None:
    db.add(token_record)