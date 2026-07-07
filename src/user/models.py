import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Enum, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base

class Role(str, enum.Enum):
  CITIZEN = "CITIZEN"
  DISPATCHER = "DISPATCHER"
  OFFICER = "OFFICER"
  MANAGER = "MANAGER"
  ADMIN = "ADMIN"

class User(Base):
  __tablename__ = "users"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  email = Column(String, unique=True, index=True, nullable=False)
  hashed_password = Column(String, nullable=False)
  first_name = Column(String, nullable=False)
  last_name = Column(String, nullable=False)
  role = Column(Enum(Role), default=Role.CITIZEN)
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), nullable=True)
  is_active = Column(Boolean, default=True)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

  # Relationship to history (for audit trail)
  history = relationship("UserHistory", back_populates="user")

class UserHistory(Base):
  __tablename__ = "user_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
  
  # Snapshot of the user data
  email = Column(String)
  first_name = Column(String)
  last_name = Column(String)
  role = Column(Enum(Role))
  
  # Audit metadata
  changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  changed_by_user_id = Column(UUID(as_uuid=True))
  change_reason = Column(String, nullable=False)

  user = relationship("User", back_populates="history")