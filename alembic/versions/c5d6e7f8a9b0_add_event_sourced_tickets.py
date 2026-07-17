"""Add event-sourced tickets and projected parallel workflow tasks.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TICKET_CATEGORIES = (
  "INFRASTRUCTURE",
  "CLEANING",
  "SAFETY",
  "NOISE",
  "OTHER",
)
_TICKET_VISIBILITIES = ("PUBLIC", "PRIVATE")
_TICKET_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "REJECTED", "CANCELLED")
_WORKFLOW_STATES = (
  "NEW",
  "AWAITING_PRIMARY_ASSIGNMENT",
  "IN_PROGRESS",
  "WAITING_FOR_CITIZEN",
  "WAITING_FOR_APPROVAL",
  "COMPLETED",
)
_EVENT_TYPES = (
  "TICKET_SUBMITTED",
  "TICKET_DETAILS_UPDATED",
  "TICKET_CANCELLED",
  "TICKET_DISPATCHED",
  "PRIMARY_OFFICER_ASSIGNED",
  "CURRENT_RESPONSIBLE_CHANGED",
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
)
_WORK_ITEM_KINDS = ("COSIGNATURE", "CONSULTATION", "APPROVAL")
_WORK_ITEM_STATUSES = ("OPEN", "COMPLETED", "CANCELLED")


def _quoted(values: tuple[str, ...]) -> str:
  """Builds a SQL string literal list for portable check constraints."""

  return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
  op.create_table(
    "tickets",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("title", sa.String(length=255), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("category", sa.String(length=32), nullable=False),
    sa.Column("creator_user_id", sa.UUID(), nullable=False),
    sa.Column("office_id", sa.UUID(), nullable=True),
    sa.Column("address_id", sa.UUID(), nullable=True),
    sa.Column("visibility", sa.String(length=16), nullable=False),
    sa.Column("public_status", sa.String(length=32), nullable=False),
    sa.Column("public_status_message", sa.String(length=500), nullable=True),
    sa.Column("workflow_state", sa.String(length=48), nullable=False),
    sa.Column("primary_officer_id", sa.UUID(), nullable=True),
    sa.Column("current_responsible_user_id", sa.UUID(), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
      f"category IN ({_quoted(_TICKET_CATEGORIES)})",
      name="ck_tickets_category",
    ),
    sa.CheckConstraint(
      f"visibility IN ({_quoted(_TICKET_VISIBILITIES)})",
      name="ck_tickets_visibility",
    ),
    sa.CheckConstraint(
      f"public_status IN ({_quoted(_TICKET_STATUSES)})",
      name="ck_tickets_public_status",
    ),
    sa.CheckConstraint(
      f"workflow_state IN ({_quoted(_WORKFLOW_STATES)})",
      name="ck_tickets_workflow_state",
    ),
    sa.CheckConstraint("version >= 1", name="ck_tickets_version_positive"),
    sa.ForeignKeyConstraint(["address_id"], ["addresses.id"]),
    sa.ForeignKeyConstraint(["creator_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["office_id"], ["offices.id"]),
    sa.ForeignKeyConstraint(["primary_officer_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["current_responsible_user_id"], ["users.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("address_id", name="uq_tickets_address_id"),
  )
  op.create_index("ix_tickets_category", "tickets", ["category"])
  op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
  op.create_index("ix_tickets_creator_user_id", "tickets", ["creator_user_id"])
  op.create_index("ix_tickets_current_responsible_user_id", "tickets", ["current_responsible_user_id"])
  op.create_index("ix_tickets_office_id", "tickets", ["office_id"])
  op.create_index("ix_tickets_primary_officer_id", "tickets", ["primary_officer_id"])
  op.create_index("ix_tickets_public_status", "tickets", ["public_status"])
  op.create_index("ix_tickets_workflow_state", "tickets", ["workflow_state"])

  op.create_table(
    "ticket_events",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("ticket_id", sa.UUID(), nullable=False),
    sa.Column("sequence_number", sa.Integer(), nullable=False),
    sa.Column("event_type", sa.String(length=64), nullable=False),
    sa.Column("actor_user_id", sa.UUID(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("citizen_visible", sa.Boolean(), nullable=False),
    sa.Column("public_status", sa.String(length=32), nullable=True),
    sa.Column("public_message", sa.String(length=500), nullable=True),
    sa.CheckConstraint(
      f"event_type IN ({_quoted(_EVENT_TYPES)})",
      name="ck_ticket_events_event_type",
    ),
    sa.CheckConstraint(
      f"public_status IS NULL OR public_status IN ({_quoted(_TICKET_STATUSES)})",
      name="ck_ticket_events_public_status",
    ),
    sa.CheckConstraint("sequence_number >= 1", name="ck_ticket_events_sequence_positive"),
    sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "ticket_id",
      "sequence_number",
      name="uq_ticket_events_ticket_sequence",
    ),
  )
  op.create_index("ix_ticket_events_actor_user_id", "ticket_events", ["actor_user_id"])
  op.create_index("ix_ticket_events_ticket_id", "ticket_events", ["ticket_id"])

  op.create_table(
    "ticket_work_items",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("ticket_id", sa.UUID(), nullable=False),
    sa.Column("group_id", sa.UUID(), nullable=False),
    sa.Column("kind", sa.String(length=32), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("assignee_user_id", sa.UUID(), nullable=False),
    sa.Column("requested_by_user_id", sa.UUID(), nullable=False),
    sa.Column("return_to_user_id", sa.UUID(), nullable=False),
    sa.Column("requested_event_id", sa.UUID(), nullable=False),
    sa.Column("completed_event_id", sa.UUID(), nullable=True),
    sa.Column("is_blocking", sa.Boolean(), nullable=False),
    sa.Column("comment", sa.String(length=1000), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
      f"kind IN ({_quoted(_WORK_ITEM_KINDS)})",
      name="ck_ticket_work_items_kind",
    ),
    sa.CheckConstraint(
      f"status IN ({_quoted(_WORK_ITEM_STATUSES)})",
      name="ck_ticket_work_items_status",
    ),
    sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["completed_event_id"], ["ticket_events.id"]),
    sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["requested_event_id"], ["ticket_events.id"]),
    sa.ForeignKeyConstraint(["return_to_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index("ix_ticket_work_items_assignee_user_id", "ticket_work_items", ["assignee_user_id"])
  op.create_index("ix_ticket_work_items_group_id", "ticket_work_items", ["group_id"])
  op.create_index("ix_ticket_work_items_status", "ticket_work_items", ["status"])
  op.create_index("ix_ticket_work_items_ticket_id", "ticket_work_items", ["ticket_id"])


def downgrade() -> None:
  op.drop_index("ix_ticket_work_items_ticket_id", table_name="ticket_work_items")
  op.drop_index("ix_ticket_work_items_status", table_name="ticket_work_items")
  op.drop_index("ix_ticket_work_items_group_id", table_name="ticket_work_items")
  op.drop_index("ix_ticket_work_items_assignee_user_id", table_name="ticket_work_items")
  op.drop_table("ticket_work_items")

  op.drop_index("ix_ticket_events_ticket_id", table_name="ticket_events")
  op.drop_index("ix_ticket_events_actor_user_id", table_name="ticket_events")
  op.drop_table("ticket_events")

  op.drop_index("ix_tickets_workflow_state", table_name="tickets")
  op.drop_index("ix_tickets_public_status", table_name="tickets")
  op.drop_index("ix_tickets_primary_officer_id", table_name="tickets")
  op.drop_index("ix_tickets_office_id", table_name="tickets")
  op.drop_index("ix_tickets_current_responsible_user_id", table_name="tickets")
  op.drop_index("ix_tickets_creator_user_id", table_name="tickets")
  op.drop_index("ix_tickets_created_at", table_name="tickets")
  op.drop_index("ix_tickets_category", table_name="tickets")
  op.drop_table("tickets")
