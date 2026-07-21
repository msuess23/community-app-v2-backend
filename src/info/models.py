"""Relational CRUD models for public authority information notices."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  CheckConstraint,
  Column,
  DateTime,
  Enum,
  ForeignKey,
  Index,
  String,
  Text,
  text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base
from src.media.models import ImageMetadataMixin


class InfoCategory(str, enum.Enum):
  """Category values retained from the original Community App backend."""

  EVENT = "EVENT"
  CONSTRUCTION = "CONSTRUCTION"
  MAINTENANCE = "MAINTENANCE"
  ANNOUNCEMENT = "ANNOUNCEMENT"
  OTHER = "OTHER"


class InfoStatus(str, enum.Enum):
  """Simple public lifecycle state without a workflow engine."""

  SCHEDULED = "SCHEDULED"
  ACTIVE = "ACTIVE"
  DONE = "DONE"
  CANCELLED = "CANCELLED"


class InfoSortField(str, enum.Enum):
  """Allowed deterministic sort columns for info lists."""

  STARTS_AT = "starts_at"
  ENDS_AT = "ends_at"
  CREATED_AT = "created_at"
  UPDATED_AT = "updated_at"
  TITLE = "title"


class Info(Base):
  """One mutable information notice managed through ordinary CRUD."""

  __tablename__ = "infos"
  __table_args__ = (
    CheckConstraint("ends_at > starts_at", name="ck_infos_time_order"),
    CheckConstraint(
      "category IN ('EVENT', 'CONSTRUCTION', 'MAINTENANCE', "
      "'ANNOUNCEMENT', 'OTHER')",
      name="ck_infos_category",
    ),
    CheckConstraint(
      "current_status IN ('SCHEDULED', 'ACTIVE', 'DONE', 'CANCELLED')",
      name="ck_infos_current_status",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  title = Column(String(255), nullable=False)
  description = Column(Text, nullable=True)
  category = Column(
    Enum(InfoCategory, native_enum=False, length=32),
    nullable=False,
    index=True,
  )
  office_id = Column(
    UUID(as_uuid=True),
    ForeignKey("offices.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
  )
  address_id = Column(
    UUID(as_uuid=True),
    ForeignKey("addresses.id"),
    nullable=True,
    unique=True,
  )
  current_status = Column(
    Enum(InfoStatus, native_enum=False, length=16),
    nullable=False,
    default=InfoStatus.SCHEDULED,
    index=True,
  )
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    index=True,
  )
  updated_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    onupdate=lambda: datetime.now(timezone.utc),
  )
  starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
  ends_at = Column(DateTime(timezone=True), nullable=False, index=True)

  office = relationship("Office", lazy="selectin")
  # Response serialization must use explicit eager loading instead of implicit SQL.
  address = relationship(
    "Address",
    cascade="all, delete-orphan",
    single_parent=True,
    lazy="raise_on_sql",
  )
  status_entries = relationship(
    "InfoStatusEntry",
    back_populates="info",
    cascade="all, delete-orphan",
    passive_deletes=True,
  )
  images = relationship(
    "InfoImage",
    back_populates="info",
    cascade="all, delete-orphan",
    passive_deletes=True,
    order_by="InfoImage.uploaded_at, InfoImage.id",
    lazy="raise_on_sql",
  )


class InfoImage(ImageMetadataMixin, Base):
  """One current CRUD-owned image that is physically deleted with its Info."""

  __tablename__ = "info_images"
  __table_args__ = (
    CheckConstraint("size_bytes > 0", name="ck_info_images_positive_size"),
    CheckConstraint(
      "width IS NULL OR width > 0",
      name="ck_info_images_positive_width",
    ),
    CheckConstraint(
      "height IS NULL OR height > 0",
      name="ck_info_images_positive_height",
    ),
    Index(
      "uq_info_images_cover",
      "info_id",
      unique=True,
      postgresql_where=text("is_cover"),
    ),
  )

  info_id = Column(
    UUID(as_uuid=True),
    ForeignKey("infos.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  uploaded_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
    index=True,
  )

  info = relationship("Info", back_populates="images")
  uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])

  @property
  def is_active(self) -> bool:
    """Expose the shared cover-helper shape; CRUD images are always current."""

    return True


class InfoStatusEntry(Base):
  """Status message history retained only while its owning info exists."""

  __tablename__ = "info_status_entries"
  __table_args__ = (
    CheckConstraint(
      "status IN ('SCHEDULED', 'ACTIVE', 'DONE', 'CANCELLED')",
      name="ck_info_status_entries_status",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  info_id = Column(
    UUID(as_uuid=True),
    ForeignKey("infos.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  status = Column(
    Enum(InfoStatus, native_enum=False, length=16),
    nullable=False,
    index=True,
  )
  message = Column(String(1000), nullable=True)
  created_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
    index=True,
  )
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    index=True,
  )

  info = relationship("Info", back_populates="status_entries")
  created_by = relationship("User", foreign_keys=[created_by_user_id])
