import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from src.core.database import Base


class PasswordReset(Base):
  """Stores a hashed, short-lived OTP for password reset."""
  __tablename__ = "password_resets"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  email = Column(String, index=True, nullable=False)
  otp_hash = Column(String, nullable=False)
  expires_at = Column(DateTime(timezone=True), nullable=False)
  created_at = Column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
  )


class RefreshToken(Base):
  """Stores only the hash of an opaque refresh token."""
  __tablename__ = "refresh_tokens"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    index=True,
    nullable=False,
  )
  token_hash = Column(String(64), unique=True, index=True, nullable=False)
  expires_at = Column(DateTime(timezone=True), nullable=False)
  created_at = Column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc),
    nullable=False,
  )
