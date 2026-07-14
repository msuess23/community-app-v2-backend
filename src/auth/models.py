import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  CheckConstraint,
  Column,
  DateTime,
  ForeignKey,
  Integer,
  String,
  UniqueConstraint,
  func,
)
from sqlalchemy.dialects.postgresql import UUID

from src.core.database import Base


class RefreshSessionRevokeReason(str, enum.Enum):
  """Machine-readable reasons why a refresh session can no longer be used."""

  ROTATED = "ROTATED"
  LOGOUT = "LOGOUT"
  REUSE_DETECTED = "REUSE_DETECTED"
  PASSWORD_RESET = "PASSWORD_RESET"
  ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"
  AUTH_VERSION_CHANGED = "AUTH_VERSION_CHANGED"
  EXPIRED = "EXPIRED"


class PasswordReset(Base):
  """
  Stores the single active password-reset challenge for a user.

  The one-row-per-user constraint prevents ambiguous challenges. OTP attempts
  are counted on the locked row so validation and consumption are atomic.
  """

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
    CheckConstraint(
      "failed_attempts >= 0",
      name="ck_password_resets_failed_attempts_nonnegative",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
  )
  otp_hash = Column(String, nullable=False)
  failed_attempts = Column(
    Integer,
    nullable=False,
    default=0,
    server_default="0",
  )
  expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
  requested_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )


class RefreshSession(Base):
  """
  Server-side state for a rotating refresh-token family.

  Only a SHA-256 fingerprint of the bearer token is stored. The JWT itself is
  returned to the client once and never persisted in plaintext.
  """

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
    CheckConstraint(
      "(revoked_at IS NULL AND revoke_reason IS NULL) OR "
      "(revoked_at IS NOT NULL AND btrim(revoke_reason) <> '')",
      name="ck_refresh_sessions_revocation_state",
    ),
  )

  # The session id is also the refresh token's JWT ``jti`` claim.
  id = Column(UUID(as_uuid=True), primary_key=True)
  user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  family_id = Column(UUID(as_uuid=True), nullable=False, index=True)
  token_hash = Column(String(64), nullable=False, unique=True, index=True)
  expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )
  last_used_at = Column(DateTime(timezone=True), nullable=True)
  revoked_at = Column(DateTime(timezone=True), nullable=True)
  revoke_reason = Column(String(32), nullable=True)
  replaced_by_id = Column(
    UUID(as_uuid=True),
    ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
    nullable=True,
  )
