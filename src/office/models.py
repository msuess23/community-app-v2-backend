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
  UniqueConstraint,
  func,
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
    server_default=func.now(),
  )
  updated_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )
  deactivated_at = Column(DateTime(timezone=True), nullable=True)
  address_id = Column(
    UUID(as_uuid=True),
    ForeignKey("addresses.id", ondelete="RESTRICT"),
    nullable=True,
  )
  address = relationship(
    Address,
    back_populates="office",
    uselist=False,
    cascade="save-update, merge",
    single_parent=True,
  )
  history = relationship(
    "OfficeHistory",
    back_populates="office",
    order_by="OfficeHistory.valid_from",
  )

  __table_args__ = (
    CheckConstraint("btrim(name) <> ''", name="ck_offices_name_not_blank"),
    CheckConstraint(
      "name = btrim(name)",
      name="ck_offices_name_trimmed",
    ),
    CheckConstraint(
      "contact_email IS NULL OR "
      "(contact_email = lower(btrim(contact_email)) AND contact_email <> '')",
      name="ck_offices_contact_email_canonical",
    ),
    CheckConstraint(
      "updated_at >= created_at",
      name="ck_offices_updated_after_creation",
    ),
    CheckConstraint(
      "(is_active IS TRUE AND deactivated_at IS NULL) OR "
      "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
      name="ck_offices_deactivation_state",
    ),
    CheckConstraint(
      "cardinality(services) <= 50",
      name="ck_offices_services_max_items",
    ),
    CheckConstraint(
      "jsonb_typeof(opening_hours) = 'object'",
      name="ck_offices_opening_hours_object",
    ),
    UniqueConstraint("address_id", name="uq_offices_address_id"),
    Index(
      "uq_offices_active_name_ci",
      func.lower(name),
      unique=True,
      postgresql_where=is_active.is_(True),
    ),
  )


class OfficeHistory(Base):
  """Immutable snapshot of an office state immediately before a change."""

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
  services = Column(ARRAY(String), nullable=False, default=list, server_default="{}")
  opening_hours = Column(JSONB, nullable=False, default=dict, server_default="{}")
  address_snapshot = Column(JSONB, nullable=True)
  is_active = Column(Boolean, nullable=False)
  deactivated_at = Column(DateTime(timezone=True), nullable=True)

  valid_from = Column(DateTime(timezone=True), nullable=False)
  valid_to = Column(DateTime(timezone=True), nullable=False)
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
      "btrim(name) <> ''",
      name="ck_office_history_name_not_blank",
    ),
    CheckConstraint(
      "cardinality(services) <= 50",
      name="ck_office_history_services_max_items",
    ),
    CheckConstraint(
      "btrim(change_reason) <> ''",
      name="ck_office_history_change_reason_not_blank",
    ),
    CheckConstraint(
      "(is_active IS TRUE AND deactivated_at IS NULL) OR "
      "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
      name="ck_office_history_deactivation_state",
    ),
    CheckConstraint(
      "jsonb_typeof(opening_hours) = 'object'",
      name="ck_office_history_opening_hours_object",
    ),
    CheckConstraint(
      "valid_to >= valid_from",
      name="ck_office_history_valid_period",
    ),
  )
