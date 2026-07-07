import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID

from src.core.database import Base

class PasswordReset(Base):
  """
  Stores hashed OTPs for password reset requests securely.
  """
  __tablename__ = "password_resets"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  email = Column(String, index=True, nullable=False)
  otp_hash = Column(String, nullable=False)
  expires_at = Column(DateTime(timezone=True), nullable=False)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class BlacklistedToken(Base):
  """
  Stores revoked JWTs to prevent reuse after logout.
  """
  __tablename__ = "blacklisted_tokens"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  token = Column(String, unique=True, index=True, nullable=False)
  blacklisted_on = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))