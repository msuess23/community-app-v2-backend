import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  Boolean,
  CheckConstraint,
  Column,
  DateTime,
  Enum,
  ForeignKey,
  Index,
  Integer,
  String,
  func,
  text,
)
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
  email = Column(String(320), nullable=False)
  hashed_password = Column(String, nullable=False)
  first_name = Column(String, nullable=False)
  last_name = Column(String, nullable=False)
  role = Column(
    Enum(Role),
    nullable=False,
    default=Role.CITIZEN,
    server_default=Role.CITIZEN.value,
  )
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), nullable=True)
  is_active = Column(Boolean, nullable=False, default=True, server_default="true")
  auth_version = Column(Integer, nullable=False, default=0, server_default="0")
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  deactivated_at = Column(DateTime(timezone=True), nullable=True)

  history = relationship(
    "UserHistory",
    foreign_keys="UserHistory.user_id",
    back_populates="user",
    order_by="UserHistory.valid_from",
  )

  __table_args__ = (
    CheckConstraint(
      "((role IN ('CITIZEN', 'ADMIN') AND office_id IS NULL) "
      "OR (role IN ('DISPATCHER', 'OFFICER', 'MANAGER') "
      "AND office_id IS NOT NULL))",
      name="ck_users_role_office_assignment",
    ),
    Index("uq_users_email_ci", func.lower(email), unique=True),
  )


class UserHistory(Base):
  """Temporal snapshot of a user version, valid on [valid_from, valid_to)."""

  __tablename__ = "user_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="RESTRICT"),
    nullable=False,
    index=True,
  )

  email = Column(String(320), nullable=False)
  first_name = Column(String, nullable=False)
  last_name = Column(String, nullable=False)
  role = Column(Enum(Role), nullable=False)
  office_id = Column(
    UUID(as_uuid=True),
    ForeignKey("offices.id", ondelete="RESTRICT"),
    nullable=True,
  )
  is_active = Column(Boolean, nullable=False)
  deactivated_at = Column(DateTime(timezone=True), nullable=True)

  valid_from = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  valid_to = Column(DateTime(timezone=True), nullable=True)
  changed_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="RESTRICT"),
    nullable=False,
  )
  change_reason = Column(String(500), nullable=False)

  user = relationship(
    "User",
    foreign_keys=[user_id],
    back_populates="history",
  )
  changed_by = relationship("User", foreign_keys=[changed_by_user_id])

  __table_args__ = (
    CheckConstraint(
      "valid_to IS NULL OR valid_to >= valid_from",
      name="ck_user_history_valid_period",
    ),
    Index(
      "uq_user_history_current_version",
      "user_id",
      unique=True,
      postgresql_where=text("valid_to IS NULL"),
    ),
  )
