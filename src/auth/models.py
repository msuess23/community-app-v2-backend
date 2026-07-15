import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from src.core.database import Base


class PasswordReset(Base):
  """Stores the currently valid password-reset OTP for a user."""

  __tablename__ = "password_resets"
  __table_args__ = (
    UniqueConstraint("user_id", name="uq_password_resets_user_id"),
    CheckConstraint(
      "btrim(otp_hash) <> ''",
      name="ck_password_resets_otp_hash_not_blank",
    ),
    CheckConstraint(
      "expires_at > requested_at",
      name="ck_password_resets_expiry_after_request",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
  )
  otp_hash = Column(String, nullable=False)
  expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
  requested_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )


class RefreshSession(Base):
  """A single, hashed refresh token used for login-session rotation."""

  __tablename__ = "refresh_sessions"
  __table_args__ = (
    CheckConstraint(
      "length(token_hash) = 64",
      name="ck_refresh_sessions_token_hash_length",
    ),
    CheckConstraint(
      "expires_at > created_at",
      name="ck_refresh_sessions_expiry_after_creation",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  token_hash = Column(String(64), nullable=False, unique=True, index=True)
  expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )
