"""SQLAlchemy read models and append-only event records for tickets."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  Boolean,
  Column,
  DateTime,
  Enum,
  ForeignKey,
  Integer,
  String,
  Text,
  UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.core.database import Base
from src.ticket.events import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
  TicketWorkItemKind,
  TicketWorkItemOutcome,
  TicketWorkItemStatus,
)


class TicketSortField(str, enum.Enum):
  """Allowed sort columns for ticket list endpoints."""

  CREATED_AT = "created_at"
  UPDATED_AT = "updated_at"
  TITLE = "title"
  STATUS = "status"


class Ticket(Base):
  """Current ticket projection used for lists and detail queries."""

  __tablename__ = "tickets"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  title = Column(String(255), nullable=False)
  description = Column(Text, nullable=True)
  category = Column(
    Enum(TicketCategory, native_enum=False, length=32),
    nullable=False,
    index=True,
  )
  creator_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
    index=True,
  )
  office_id = Column(
    UUID(as_uuid=True),
    ForeignKey("offices.id"),
    nullable=True,
    index=True,
  )
  address_id = Column(
    UUID(as_uuid=True),
    ForeignKey("addresses.id"),
    nullable=True,
    unique=True,
  )
  visibility = Column(
    Enum(TicketVisibility, native_enum=False, length=16),
    nullable=False,
    default=TicketVisibility.PUBLIC,
  )
  public_status = Column(
    Enum(TicketStatus, native_enum=False, length=32),
    nullable=False,
    default=TicketStatus.OPEN,
    index=True,
  )
  public_status_message = Column(String(500), nullable=True)
  workflow_state = Column(
    Enum(TicketWorkflowState, native_enum=False, length=48),
    nullable=False,
    default=TicketWorkflowState.NEW,
    index=True,
  )

  # The primary officer remains the permanent case owner.  The current
  # responsible user may temporarily change during escalation or citizen input.
  primary_officer_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
    index=True,
  )
  current_responsible_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
    index=True,
  )
  pending_return_to_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=True,
    index=True,
  )

  version = Column(Integer, nullable=False, default=1)
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
  resolved_at = Column(DateTime(timezone=True), nullable=True)
  cancelled_at = Column(DateTime(timezone=True), nullable=True)

  creator = relationship("User", foreign_keys=[creator_user_id], lazy="selectin")
  office = relationship("Office", lazy="selectin")
  address = relationship(
    "Address",
    cascade="all, delete-orphan",
    single_parent=True,
    lazy="selectin",
  )
  primary_officer = relationship("User", foreign_keys=[primary_officer_id])
  current_responsible_user = relationship(
    "User",
    foreign_keys=[current_responsible_user_id],
  )
  pending_return_to_user = relationship(
    "User",
    foreign_keys=[pending_return_to_user_id],
  )
  events = relationship(
    "TicketEvent",
    back_populates="ticket",
    order_by="TicketEvent.sequence_number",
    cascade="all, delete-orphan",
  )
  work_items = relationship(
    "TicketWorkItem",
    back_populates="ticket",
    cascade="all, delete-orphan",
  )


class TicketEvent(Base):
  """Immutable event belonging to one ticket aggregate stream."""

  __tablename__ = "ticket_events"
  __table_args__ = (
    UniqueConstraint(
      "ticket_id",
      "sequence_number",
      name="uq_ticket_events_ticket_sequence",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  ticket_id = Column(
    UUID(as_uuid=True),
    ForeignKey("tickets.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  sequence_number = Column(Integer, nullable=False)
  event_type = Column(
    Enum(TicketEventType, native_enum=False, length=64),
    nullable=False,
  )
  actor_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
    index=True,
  )
  occurred_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  payload = Column(JSONB, nullable=False, default=dict)
  citizen_visible = Column(Boolean, nullable=False, default=False)
  public_status = Column(
    Enum(TicketStatus, native_enum=False, length=32),
    nullable=True,
  )
  public_message = Column(String(500), nullable=True)

  ticket = relationship("Ticket", back_populates="events")
  actor = relationship("User", foreign_keys=[actor_user_id])


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
