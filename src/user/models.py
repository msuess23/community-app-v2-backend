import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Enum, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base

class Role(str, enum.Enum):
  """Define the supported citizen and authority user roles."""

  CITIZEN = "CITIZEN"
  DISPATCHER = "DISPATCHER"
  OFFICER = "OFFICER"
  MANAGER = "MANAGER"
  ADMIN = "ADMIN"

class UserSortField(str, enum.Enum):
  """Define supported sort fields for user list queries."""

  CREATED_AT = "created_at"
  EMAIL = "email"
  FIRST_NAME = "first_name"
  LAST_NAME = "last_name"
  ROLE = "role"


class User(Base):
  """Persist the current user account and role assignment."""

  __tablename__ = "users"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  email = Column(String, index=True, nullable=False)
  hashed_password = Column(String, nullable=False)
  first_name = Column(String, nullable=False)
  last_name = Column(String, nullable=False)
  role = Column(Enum(Role), nullable=False, default=Role.CITIZEN)
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), nullable=True)
  is_active = Column(Boolean, nullable=False, default=True)
  created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
  deactivated_at = Column(DateTime(timezone=True), nullable=True)

  # Relationship to history (for audit trail)
  history = relationship(
    "UserHistory",
    back_populates="user",
    foreign_keys="UserHistory.user_id",
  )

class UserHistory(Base):
  """Persist one immutable snapshot of a user account change."""

  __tablename__ = "user_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
  
  # Snapshot of the user data
  email = Column(String, nullable=False)
  first_name = Column(String, nullable=False)
  last_name = Column(String, nullable=False)
  role = Column(Enum(Role), nullable=False)
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), nullable=True)
  is_active = Column(Boolean, nullable=False, default=True)
  
  # Audit metadata
  changed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
  changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
  change_reason = Column(String, nullable=False)

  user = relationship(
    "User",
    back_populates="history",
    foreign_keys=[user_id],
  )