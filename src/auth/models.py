import uuid
from datetime import datetime
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
  expires_at = Column(DateTime, nullable=False)
  created_at = Column(DateTime, default=datetime.utcnow)