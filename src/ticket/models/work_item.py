"""Projected parallel workflow work items."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  Boolean, Column, DateTime, Enum, ForeignKey,
  String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base
from src.ticket.events import (
  TicketWorkItemKind, TicketWorkItemOutcome,
  TicketWorkItemStatus,
)

class TicketWorkItem(Base):
  """Projected subtask used for intentionally limited workflow parallelism.

  Several open rows with the same group_id represent a parallel review round.
  Events remain the source of truth; this table only makes task inbox queries
  efficient for the administrative client.
  """

  __tablename__ = "ticket_work_items"
  __table_args__ = (
    UniqueConstraint(
      "ticket_id",
      "group_id",
      "assignee_user_id",
      name="uq_ticket_work_items_group_assignee",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  ticket_id = Column(
    UUID(as_uuid=True),
    ForeignKey("tickets.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  group_id = Column(UUID(as_uuid=True), nullable=False, index=True)
  kind = Column(
    Enum(TicketWorkItemKind, native_enum=False, length=32),
    nullable=False,
  )
  status = Column(
    Enum(TicketWorkItemStatus, native_enum=False, length=16),
    nullable=False,
    default=TicketWorkItemStatus.OPEN,
    index=True,
  )
  outcome = Column(
    Enum(TicketWorkItemOutcome, native_enum=False, length=16),
    nullable=True,
  )
  assignee_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
    index=True,
  )
  requested_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
  )
  return_to_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
  )
  requested_event_id = Column(
    UUID(as_uuid=True),
    ForeignKey("ticket_events.id"),
    nullable=False,
  )
  completed_event_id = Column(
    UUID(as_uuid=True),
    ForeignKey("ticket_events.id"),
    nullable=True,
  )
  is_blocking = Column(Boolean, nullable=False, default=True)
  comment = Column(String(1000), nullable=True)
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  completed_at = Column(DateTime(timezone=True), nullable=True)

  ticket = relationship("Ticket", back_populates="work_items")
  assignee = relationship("User", foreign_keys=[assignee_user_id])
  requested_by = relationship("User", foreign_keys=[requested_by_user_id])
  return_to_user = relationship("User", foreign_keys=[return_to_user_id])
  requested_event = relationship("TicketEvent", foreign_keys=[requested_event_id])
  completed_event = relationship("TicketEvent", foreign_keys=[completed_event_id])
