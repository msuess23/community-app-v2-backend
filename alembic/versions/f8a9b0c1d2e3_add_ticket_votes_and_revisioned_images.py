"""Add community votes and revisioned ticket images.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EVENT_TYPES = (
  "TICKET_SUBMITTED",
  "TICKET_DETAILS_UPDATED",
  "TICKET_CANCELLED",
  "TICKET_DISPATCHED",
  "PRIMARY_OFFICER_ASSIGNED",
  "TICKET_FORWARDED",
  "PARALLEL_WORK_ITEMS_REQUESTED",
  "WORK_ITEM_COMPLETED",
  "WORK_ITEM_CANCELLED",
  "CITIZEN_RESPONSE_REQUESTED",
  "CITIZEN_RESPONDED",
  "TICKET_ESCALATED",
  "ESCALATION_APPROVED",
  "ESCALATION_REJECTED",
  "TICKET_RESOLVED",
  "TICKET_REJECTED",
  "TICKET_COMMENTED",
  "TICKET_IMAGE_ADDED",
  "TICKET_IMAGE_REMOVED",
  "TICKET_COVER_IMAGE_CHANGED",
)


def _event_type_check(values: tuple[str, ...]) -> str:
  return "event_type IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Adds vote projections and event-linked image metadata."""

  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    _event_type_check(_EVENT_TYPES),
  )

  op.create_table(
    "ticket_votes",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(
      ["ticket_id"],
      ["tickets.id"],
      name="fk_ticket_votes_ticket_id_tickets",
      ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
      ["user_id"],
      ["users.id"],
      name="fk_ticket_votes_user_id_users",
      ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_ticket_votes"),
    sa.UniqueConstraint(
      "ticket_id",
      "user_id",
      name="uq_ticket_votes_ticket_user",
    ),
  )
  op.create_index("ix_ticket_votes_ticket_id", "ticket_votes", ["ticket_id"])
  op.create_index("ix_ticket_votes_user_id", "ticket_votes", ["user_id"])

  op.create_table(
    "ticket_images",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("storage_key", sa.String(length=500), nullable=False),
    sa.Column("original_filename", sa.String(length=255), nullable=False),
    sa.Column("mime_type", sa.String(length=100), nullable=False),
    sa.Column("size_bytes", sa.BigInteger(), nullable=False),
    sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("is_cover", sa.Boolean(), nullable=False),
    sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("removed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("added_event_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("removed_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column(
      "cover_selected_event_id",
      postgresql.UUID(as_uuid=True),
      nullable=True,
    ),
    sa.CheckConstraint("size_bytes > 0", name="ck_ticket_images_positive_size"),
    sa.CheckConstraint(
      "(is_active AND removed_at IS NULL AND removed_by_user_id IS NULL) OR "
      "(NOT is_active AND removed_at IS NOT NULL AND removed_by_user_id IS NOT NULL)",
      name="ck_ticket_images_removal_state",
    ),
    sa.ForeignKeyConstraint(
      ["ticket_id"],
      ["tickets.id"],
      name="fk_ticket_images_ticket_id_tickets",
      ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
      ["uploaded_by_user_id"],
      ["users.id"],
      name="fk_ticket_images_uploaded_by_user_id_users",
    ),
    sa.ForeignKeyConstraint(
      ["removed_by_user_id"],
      ["users.id"],
      name="fk_ticket_images_removed_by_user_id_users",
    ),
    sa.ForeignKeyConstraint(
      ["added_event_id"],
      ["ticket_events.id"],
      name="fk_ticket_images_added_event_id_ticket_events",
    ),
    sa.ForeignKeyConstraint(
      ["removed_event_id"],
      ["ticket_events.id"],
      name="fk_ticket_images_removed_event_id_ticket_events",
    ),
    sa.ForeignKeyConstraint(
      ["cover_selected_event_id"],
      ["ticket_events.id"],
      name="fk_ticket_images_cover_selected_event_id_ticket_events",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_ticket_images"),
    sa.UniqueConstraint("storage_key", name="uq_ticket_images_storage_key"),
  )
  op.create_index("ix_ticket_images_ticket_id", "ticket_images", ["ticket_id"])
  op.create_index("ix_ticket_images_is_active", "ticket_images", ["is_active"])
  op.create_index(
    "uq_ticket_images_active_cover",
    "ticket_images",
    ["ticket_id"],
    unique=True,
    postgresql_where=sa.text("is_active AND is_cover"),
  )


def downgrade() -> None:
  """Removes image and vote projections and restores the former event list."""

  op.drop_index("uq_ticket_images_active_cover", table_name="ticket_images")
  op.drop_index("ix_ticket_images_is_active", table_name="ticket_images")
  op.drop_index("ix_ticket_images_ticket_id", table_name="ticket_images")
  op.drop_table("ticket_images")

  op.drop_index("ix_ticket_votes_user_id", table_name="ticket_votes")
  op.drop_index("ix_ticket_votes_ticket_id", table_name="ticket_votes")
  op.drop_table("ticket_votes")

  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    _event_type_check(_EVENT_TYPES[:-3]),
  )
