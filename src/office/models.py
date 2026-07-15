import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import ARRAY, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.core.database import Base


class OfficeSortField(str, enum.Enum):
  CREATED_AT = "created_at"
  NAME = "name"
  CONTACT_EMAIL = "contact_email"


class Office(Base):
  """A department used for routing and staff assignment."""

  __tablename__ = "offices"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  name = Column(String, nullable=False, unique=False)
  description = Column(String, nullable=True)
  contact_email = Column(String, nullable=True)
  phone = Column(String, nullable=True)
  services = Column(ARRAY(String), default=list)
  opening_hours = Column(JSONB, default=dict)
  is_active = Column(Boolean, default=True)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  deactivated_at = Column(DateTime(timezone=True), nullable=True)
  address_id = Column(
    UUID(as_uuid=True),
    ForeignKey("addresses.id"),
    nullable=True,
    unique=True,
  )
  # One-way ownership: Address has deliberately no office relationship.
  address = relationship(
    "Address",
    cascade="all, delete-orphan",
    single_parent=True,
    lazy="selectin",
  )


class OfficeHistory(Base):
  """Append-only snapshots of valid office states."""

  __tablename__ = "office_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  office_id = Column(UUID(as_uuid=True), ForeignKey("offices.id"), index=True)
  name = Column(String)
  description = Column(String, nullable=True)
  contact_email = Column(String, nullable=True)
  phone = Column(String, nullable=True)
  services = Column(ARRAY(String), default=list)
  opening_hours = Column(JSONB, default=dict)
  address_snapshot = Column(String, nullable=True)
  is_active = Column(Boolean, nullable=False, default=True)
  changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  changed_by_user_id = Column(UUID(as_uuid=True))
  change_reason = Column(String, nullable=False)
