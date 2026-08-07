"""Add appointment slots and event-sourced appointments.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SLOT_STATUSES = ("AVAILABLE", "BOOKED", "INACTIVE", "CONSUMED")
_APPOINTMENT_STATUSES = ("SCHEDULED", "CANCELLED", "COMPLETED", "NO_SHOW")
_EVENT_TYPES = (
  "APPOINTMENT_BOOKED",
  "APPOINTMENT_RESCHEDULED",
  "APPOINTMENT_CANCELLED",
  "APPOINTMENT_COMPLETED",
  "APPOINTMENT_MARKED_NO_SHOW",
  "DOCUMENT_VERSION_ADDED",
)


def _check(column: str, values: tuple[str, ...]) -> str:
  return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Create capacity slots, current projections and append-only event streams."""

  op.create_table(
    "appointment_slots",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
      "ends_at > starts_at",
      name="ck_appointment_slots_time_order",
    ),
    sa.CheckConstraint(
      _check("status", _SLOT_STATUSES),
      name="ck_appointment_slots_status",
    ),
    sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["office_id"], ["offices.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "office_id",
      "starts_at",
      "ends_at",
      name="uq_appointment_slots_office_interval",
    ),
  )
  op.create_index(
    "ix_appointment_slots_office_id",
    "appointment_slots",
    ["office_id"],
  )
  op.create_index(
    "ix_appointment_slots_starts_at",
    "appointment_slots",
    ["starts_at"],
  )
  op.create_index(
    "ix_appointment_slots_status",
    "appointment_slots",
    ["status"],
  )

  op.create_table(
    "appointments",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("current_slot_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("citizen_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("reason", sa.Text(), nullable=True),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("ends_at > starts_at", name="ck_appointments_time_order"),
    sa.CheckConstraint(
      _check("status", _APPOINTMENT_STATUSES),
      name="ck_appointments_status",
    ),
    sa.ForeignKeyConstraint(["citizen_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["current_slot_id"], ["appointment_slots.id"]),
    sa.ForeignKeyConstraint(["office_id"], ["offices.id"]),
    sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("current_slot_id", name="uq_appointments_current_slot_id"),
  )
  op.create_index("ix_appointments_citizen_id", "appointments", ["citizen_id"])
  op.create_index("ix_appointments_created_at", "appointments", ["created_at"])
  op.create_index("ix_appointments_office_id", "appointments", ["office_id"])
  op.create_index("ix_appointments_starts_at", "appointments", ["starts_at"])
  op.create_index("ix_appointments_status", "appointments", ["status"])
  op.create_index("ix_appointments_ticket_id", "appointments", ["ticket_id"])

  op.create_table(
    "appointment_events",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("sequence_number", sa.Integer(), nullable=False),
    sa.Column("event_type", sa.String(length=64), nullable=False),
    sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint(
      _check("event_type", _EVENT_TYPES),
      name="ck_appointment_events_event_type",
    ),
    sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(
      ["appointment_id"],
      ["appointments.id"],
      ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "appointment_id",
      "sequence_number",
      name="uq_appointment_events_appointment_sequence",
    ),
  )
  op.create_index(
    "ix_appointment_events_actor_user_id",
    "appointment_events",
    ["actor_user_id"],
  )
  op.create_index(
    "ix_appointment_events_appointment_id",
    "appointment_events",
    ["appointment_id"],
  )


def downgrade() -> None:
  """Remove the appointment aggregate and its capacity slots."""

  op.drop_index(
    "ix_appointment_events_appointment_id",
    table_name="appointment_events",
  )
  op.drop_index(
    "ix_appointment_events_actor_user_id",
    table_name="appointment_events",
  )
  op.drop_table("appointment_events")

  op.drop_index("ix_appointments_ticket_id", table_name="appointments")
  op.drop_index("ix_appointments_status", table_name="appointments")
  op.drop_index("ix_appointments_starts_at", table_name="appointments")
  op.drop_index("ix_appointments_office_id", table_name="appointments")
  op.drop_index("ix_appointments_created_at", table_name="appointments")
  op.drop_index("ix_appointments_citizen_id", table_name="appointments")
  op.drop_table("appointments")

  op.drop_index("ix_appointment_slots_status", table_name="appointment_slots")
  op.drop_index("ix_appointment_slots_starts_at", table_name="appointment_slots")
  op.drop_index("ix_appointment_slots_office_id", table_name="appointment_slots")
  op.drop_table("appointment_slots")
