import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  ARRAY,
  Boolean,
  CheckConstraint,
  Column,
  DateTime,
  ForeignKey,
  Index,
  String,
  func,
  text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.address.models import Address
from src.core.database import Base


class Office(Base):
  """Department or authority office used for workflow routing."""

  __tablename__ = "offices"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  name = Column(String(150), nullable=False)
  description = Column(String(500), nullable=True)
  contact_email = Column(String(320), nullable=True)
  phone = Column(String(50), nullable=True)
  services = Column(ARRAY(String), nullable=False, default=list, server_default="{}")
  opening_hours = Column(JSONB, nullable=False, default=dict, server_default="{}")
  is_active = Column(Boolean, nullable=False, default=True, server_default="true")
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  deactivated_at = Column(DateTime(timezone=True), nullable=True)
  address_id = Column(UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True)
  address = relationship(Address, backref="offices")
  history = relationship(
    "OfficeHistory",
    back_populates="office",
    order_by="OfficeHistory.valid_from",
  )

  __table_args__ = (
    Index(
      "uq_offices_active_name_ci",
      func.lower(name),
      unique=True,
      postgresql_where=is_active.is_(True),
    ),
  )


class OfficeHistory(Base):
  """Temporal snapshot of an office version, valid on [valid_from, valid_to)."""

  __tablename__ = "office_history"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  office_id = Column(
    UUID(as_uuid=True),
    ForeignKey("offices.id", ondelete="RESTRICT"),
    nullable=False,
    index=True,
  )

  name = Column(String(150), nullable=False)
  description = Column(String(500), nullable=True)
  contact_email = Column(String(320), nullable=True)
  phone = Column(String(50), nullable=True)
  services = Column(ARRAY(String), nullable=False, default=list)
  opening_hours = Column(JSONB, nullable=False, default=dict)
  address_snapshot = Column(JSONB, nullable=True)
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

  office = relationship("Office", back_populates="history")
  changed_by = relationship("User", foreign_keys=[changed_by_user_id])

  __table_args__ = (
    CheckConstraint(
      "valid_to IS NULL OR valid_to >= valid_from",
      name="ck_office_history_valid_period",
    ),
    Index(
      "uq_office_history_current_version",
      "office_id",
      unique=True,
      postgresql_where=text("valid_to IS NULL"),
    ),
  )
