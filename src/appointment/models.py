"""Relational slot data, appointment read models and append-only events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
  CheckConstraint,
  Column,
  DateTime,
  Enum,
  ForeignKey,
  Integer,
  Text,
  UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.appointment.domain import (
  AppointmentEventType,
  AppointmentSlotStatus,
  AppointmentStatus,
)
from src.core.database import Base


class AppointmentSlot(Base):
  """One bookable capacity interval offered by an office."""

  __tablename__ = "appointment_slots"
  __table_args__ = (
    CheckConstraint("ends_at > starts_at", name="ck_appointment_slots_time_order"),
    CheckConstraint(
      "status IN ('AVAILABLE', 'BOOKED', 'INACTIVE', 'CONSUMED')",
      name="ck_appointment_slots_status",
    ),
    UniqueConstraint(
      "office_id",
      "starts_at",
      "ends_at",
      name="uq_appointment_slots_office_interval",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  office_id = Column(
    UUID(as_uuid=True),
    ForeignKey("offices.id"),
    nullable=False,
    index=True,
  )
  starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
  ends_at = Column(DateTime(timezone=True), nullable=False)
  status = Column(
    Enum(AppointmentSlotStatus, native_enum=False, length=16),
    nullable=False,
    default=AppointmentSlotStatus.AVAILABLE,
    index=True,
  )
  created_by_user_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
  )
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
  )
  updated_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    onupdate=lambda: datetime.now(timezone.utc),
  )

  office = relationship("Office")
  created_by = relationship("User", foreign_keys=[created_by_user_id])


class Appointment(Base):
  """Current read model synchronized with the appointment event stream."""

  __tablename__ = "appointments"
  __table_args__ = (
    CheckConstraint("ends_at > starts_at", name="ck_appointments_time_order"),
    CheckConstraint(
      "status IN ('SCHEDULED', 'CANCELLED', 'COMPLETED', 'NO_SHOW')",
      name="ck_appointments_status",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  current_slot_id = Column(
    UUID(as_uuid=True),
    ForeignKey("appointment_slots.id"),
    nullable=True,
    unique=True,
  )
  office_id = Column(
    UUID(as_uuid=True),
    ForeignKey("offices.id"),
    nullable=False,
    index=True,
  )
  citizen_id = Column(
    UUID(as_uuid=True),
    ForeignKey("users.id"),
    nullable=False,
    index=True,
  )
  ticket_id = Column(
    UUID(as_uuid=True),
    ForeignKey("tickets.id"),
    nullable=True,
    index=True,
  )
  reason = Column(Text, nullable=True)
  status = Column(
    Enum(AppointmentStatus, native_enum=False, length=16),
    nullable=False,
    default=AppointmentStatus.SCHEDULED,
    index=True,
  )
  starts_at = Column(DateTime(timezone=True), nullable=False, index=True)
  ends_at = Column(DateTime(timezone=True), nullable=False)
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
  cancelled_at = Column(DateTime(timezone=True), nullable=True)
  completed_at = Column(DateTime(timezone=True), nullable=True)

  current_slot = relationship("AppointmentSlot", foreign_keys=[current_slot_id])
  office = relationship("Office")
  citizen = relationship("User", foreign_keys=[citizen_id])
  ticket = relationship("Ticket")
  events = relationship(
    "AppointmentEvent",
    back_populates="appointment",
    order_by="AppointmentEvent.sequence_number",
    cascade="all, delete-orphan",
  )


class AppointmentEvent(Base):
  """Immutable event belonging to one appointment aggregate stream."""

  __tablename__ = "appointment_events"
  __table_args__ = (
    CheckConstraint(
      "event_type IN ('APPOINTMENT_BOOKED', 'APPOINTMENT_RESCHEDULED', "
      "'APPOINTMENT_CANCELLED', 'APPOINTMENT_COMPLETED', "
      "'APPOINTMENT_MARKED_NO_SHOW', 'DOCUMENT_VERSION_ADDED')",
      name="ck_appointment_events_event_type",
    ),
    UniqueConstraint(
      "appointment_id",
      "sequence_number",
      name="uq_appointment_events_appointment_sequence",
    ),
  )

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  appointment_id = Column(
    UUID(as_uuid=True),
    ForeignKey("appointments.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  sequence_number = Column(Integer, nullable=False)
  event_type = Column(
    Enum(AppointmentEventType, native_enum=False, length=64),
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

  appointment = relationship("Appointment", back_populates="events")
  actor = relationship("User", foreign_keys=[actor_user_id])
