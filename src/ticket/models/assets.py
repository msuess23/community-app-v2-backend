"""Revisioned ticket image projection models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey,
  Index, String, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base

class TicketImage(Base):
  """Current image projection backed by immutable ticket media events.

  Removing an image only deactivates this projection.  The original file and
  metadata stay available to authorized staff so the event history remains
  verifiable.
  """

  __tablename__ = "ticket_images"
  __table_args__ = (
    CheckConstraint("size_bytes > 0", name="ck_ticket_images_positive_size"),
    CheckConstraint(
      "(is_active AND removed_at IS NULL AND removed_by_user_id IS NULL) OR "
      "(NOT is_active AND removed_at IS NOT NULL AND removed_by_user_id IS NOT NULL)",
      name="ck_ticket_images_removal_state",
    ),
    Index(
      "uq_ticket_images_active_cover",
      "ticket_id",
      unique=True,
      postgresql_where=text("is_active AND is_cover"),
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  ticket_id = Column(
    UUID(as_uuid=True),
    ForeignKey("tickets.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  storage_key = Column(String(500), nullable=False, unique=True)
  original_filename = Column(String(255), nullable=False)
  mime_type = Column(String(100), nullable=False)
  size_bytes = Column(BigInteger, nullable=False)
  uploaded_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
  )
  uploaded_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  is_active = Column(Boolean, nullable=False, default=True, index=True)
  is_cover = Column(Boolean, nullable=False, default=False)
  removed_at = Column(DateTime(timezone=True), nullable=True)
  removed_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
  )
  added_event_id = Column(
    UUID(as_uuid=True),
    ForeignKey("ticket_events.id"),
    nullable=False,
  )
  removed_event_id = Column(
    UUID(as_uuid=True),
    ForeignKey("ticket_events.id"),
    nullable=True,
  )
  cover_selected_event_id = Column(
    UUID(as_uuid=True),
    ForeignKey("ticket_events.id"),
    nullable=True,
  )

  ticket = relationship("Ticket", back_populates="images")
  uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])
  removed_by = relationship("User", foreign_keys=[removed_by_user_id])
  added_event = relationship("TicketEvent", foreign_keys=[added_event_id])
  removed_event = relationship("TicketEvent", foreign_keys=[removed_event_id])
  cover_selected_event = relationship(
    "TicketEvent",
    foreign_keys=[cover_selected_event_id],
  )
