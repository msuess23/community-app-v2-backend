"""Simplify the ticket workflow and remove community votes.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EVENT_TYPES = (
  "TICKET_SUBMITTED",
  "TICKET_DETAILS_UPDATED",
  "TICKET_CANCELLED",
  "TICKET_DISPATCHED",
  "PRIMARY_OFFICER_ASSIGNED",
  "TICKET_FORWARDED",
  "COSIGNATURE_REQUESTED",
  "TICKET_COSIGNED",
  "CITIZEN_RESPONSE_REQUESTED",
  "CITIZEN_RESPONDED",
  "TICKET_ESCALATED",
  "ESCALATION_DECIDED",
  "TICKET_COMPLETED",
  "TICKET_COMMENTED",
  "TICKET_IMAGE_ADDED",
  "TICKET_IMAGE_REMOVED",
  "TICKET_COVER_IMAGE_CHANGED",
)

_WORKFLOW_STATES = (
  "NEW",
  "AWAITING_PRIMARY_ASSIGNMENT",
  "IN_PROGRESS",
  "WAITING_FOR_COSIGNATURE",
  "WAITING_FOR_CITIZEN",
  "WAITING_FOR_DECISION",
  "COMPLETED",
)


def _check(column: str, values: tuple[str, ...]) -> str:
  return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Remove parallel task/vote projections and normalize workflow events."""

  op.drop_index("ix_ticket_work_items_ticket_id", table_name="ticket_work_items")
  op.drop_index("ix_ticket_work_items_status", table_name="ticket_work_items")
  op.drop_index("ix_ticket_work_items_group_id", table_name="ticket_work_items")
  op.drop_index("ix_ticket_work_items_assignee_user_id", table_name="ticket_work_items")
  op.drop_table("ticket_work_items")

  op.drop_index("ix_ticket_votes_user_id", table_name="ticket_votes")
  op.drop_index("ix_ticket_votes_ticket_id", table_name="ticket_votes")
  op.drop_table("ticket_votes")

  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.drop_constraint("ck_ticket_events_public_status", "ticket_events", type_="check")
  op.drop_constraint(
    "uq_ticket_events_ticket_sequence",
    "ticket_events",
    type_="unique",
  )

  # Parallel work-item events did not change ticket business fields. Removing
  # them and compacting the sequence therefore preserves the aggregate state.
  op.execute(
    "DELETE FROM ticket_events WHERE event_type IN ("
    "'PARALLEL_WORK_ITEMS_REQUESTED', 'WORK_ITEM_COMPLETED', "
    "'WORK_ITEM_CANCELLED')"
  )
  op.execute(
    "UPDATE ticket_events SET event_type = 'ESCALATION_DECIDED', "
    "payload = payload || jsonb_build_object('decision', 'APPROVED') "
    "WHERE event_type = 'ESCALATION_APPROVED'"
  )
  op.execute(
    "UPDATE ticket_events SET event_type = 'ESCALATION_DECIDED', "
    "payload = payload || jsonb_build_object('decision', 'REJECTED') "
    "WHERE event_type = 'ESCALATION_REJECTED'"
  )
  op.execute(
    "UPDATE ticket_events SET event_type = 'TICKET_COMPLETED', "
    "payload = payload || jsonb_build_object('outcome', 'RESOLVED') "
    "WHERE event_type = 'TICKET_RESOLVED'"
  )
  op.execute(
    "UPDATE ticket_events SET event_type = 'TICKET_COMPLETED', "
    "payload = payload || jsonb_build_object('outcome', 'REJECTED') "
    "WHERE event_type = 'TICKET_REJECTED'"
  )
  op.execute(
    "WITH ordered AS ("
    "  SELECT id, row_number() OVER (PARTITION BY ticket_id ORDER BY sequence_number) AS new_sequence "
    "  FROM ticket_events"
    ") UPDATE ticket_events AS event SET sequence_number = ordered.new_sequence "
    "FROM ordered WHERE event.id = ordered.id"
  )
  op.execute(
    "UPDATE tickets AS ticket SET version = COALESCE(("
    "  SELECT max(event.sequence_number) FROM ticket_events AS event "
    "  WHERE event.ticket_id = ticket.id"
    "), 1)"
  )

  op.drop_column("ticket_events", "public_message")
  op.drop_column("ticket_events", "public_status")
  op.drop_column("ticket_events", "citizen_visible")
  op.create_unique_constraint(
    "uq_ticket_events_ticket_sequence",
    "ticket_events",
    ["ticket_id", "sequence_number"],
  )
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    _check("event_type", _EVENT_TYPES),
  )

  op.drop_constraint("ck_tickets_workflow_state", "tickets", type_="check")
  op.execute(
    "UPDATE tickets SET workflow_state = 'WAITING_FOR_DECISION' "
    "WHERE workflow_state = 'WAITING_FOR_APPROVAL'"
  )
  op.create_check_constraint(
    "ck_tickets_workflow_state",
    "tickets",
    _check("workflow_state", _WORKFLOW_STATES),
  )
  op.alter_column("tickets", "resolved_at", new_column_name="completed_at")


def downgrade() -> None:
  """Restore the former schema when no new simplified-only events exist."""

  op.execute(
    "DO $$ BEGIN "
    "IF EXISTS (SELECT 1 FROM ticket_events WHERE event_type IN ("
    "'COSIGNATURE_REQUESTED', 'TICKET_COSIGNED')) THEN "
    "RAISE EXCEPTION 'Cannot downgrade tickets containing sequential cosignature events'; "
    "END IF; END $$"
  )

  op.alter_column("tickets", "completed_at", new_column_name="resolved_at")
  op.drop_constraint("ck_tickets_workflow_state", "tickets", type_="check")
  op.execute(
    "UPDATE tickets SET workflow_state = 'WAITING_FOR_APPROVAL' "
    "WHERE workflow_state = 'WAITING_FOR_DECISION'"
  )
  op.create_check_constraint(
    "ck_tickets_workflow_state",
    "tickets",
    "workflow_state IN ('NEW', 'AWAITING_PRIMARY_ASSIGNMENT', 'IN_PROGRESS', "
    "'WAITING_FOR_CITIZEN', 'WAITING_FOR_APPROVAL', 'COMPLETED')",
  )

  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.add_column(
    "ticket_events",
    sa.Column("citizen_visible", sa.Boolean(), nullable=False, server_default=sa.false()),
  )
  op.add_column(
    "ticket_events",
    sa.Column("public_status", sa.String(length=32), nullable=True),
  )
  op.add_column(
    "ticket_events",
    sa.Column("public_message", sa.String(length=500), nullable=True),
  )
  op.execute(
    "UPDATE ticket_events SET event_type = CASE "
    "WHEN payload->>'decision' = 'APPROVED' THEN 'ESCALATION_APPROVED' "
    "ELSE 'ESCALATION_REJECTED' END, payload = payload - 'decision' "
    "WHERE event_type = 'ESCALATION_DECIDED'"
  )
  op.execute(
    "UPDATE ticket_events SET event_type = CASE "
    "WHEN payload->>'outcome' = 'RESOLVED' THEN 'TICKET_RESOLVED' "
    "ELSE 'TICKET_REJECTED' END, payload = payload - 'outcome' "
    "WHERE event_type = 'TICKET_COMPLETED'"
  )
  op.create_check_constraint(
    "ck_ticket_events_public_status",
    "ticket_events",
    "public_status IS NULL OR public_status IN ("
    "'OPEN', 'IN_PROGRESS', 'RESOLVED', 'REJECTED', 'CANCELLED')",
  )
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    "event_type IN ("
    "'TICKET_SUBMITTED', 'TICKET_DETAILS_UPDATED', 'TICKET_CANCELLED', "
    "'TICKET_DISPATCHED', 'PRIMARY_OFFICER_ASSIGNED', 'TICKET_FORWARDED', "
    "'PARALLEL_WORK_ITEMS_REQUESTED', 'WORK_ITEM_COMPLETED', "
    "'WORK_ITEM_CANCELLED', 'CITIZEN_RESPONSE_REQUESTED', "
    "'CITIZEN_RESPONDED', 'TICKET_ESCALATED', 'ESCALATION_APPROVED', "
    "'ESCALATION_REJECTED', 'TICKET_RESOLVED', 'TICKET_REJECTED', "
    "'TICKET_COMMENTED', 'TICKET_IMAGE_ADDED', 'TICKET_IMAGE_REMOVED', "
    "'TICKET_COVER_IMAGE_CHANGED')",
  )

  op.create_table(
    "ticket_votes",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("ticket_id", "user_id", name="uq_ticket_votes_ticket_user"),
  )
  op.create_index("ix_ticket_votes_ticket_id", "ticket_votes", ["ticket_id"])
  op.create_index("ix_ticket_votes_user_id", "ticket_votes", ["user_id"])

  op.create_table(
    "ticket_work_items",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("kind", sa.String(length=32), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("outcome", sa.String(length=16), nullable=True),
    sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("return_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("requested_event_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("completed_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("is_blocking", sa.Boolean(), nullable=False),
    sa.Column("comment", sa.String(length=1000), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
    sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["return_to_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["requested_event_id"], ["ticket_events.id"]),
    sa.ForeignKeyConstraint(["completed_event_id"], ["ticket_events.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "ticket_id",
      "group_id",
      "assignee_user_id",
      name="uq_ticket_work_items_group_assignee",
    ),
  )
  op.create_index("ix_ticket_work_items_ticket_id", "ticket_work_items", ["ticket_id"])
  op.create_index("ix_ticket_work_items_status", "ticket_work_items", ["status"])
  op.create_index("ix_ticket_work_items_group_id", "ticket_work_items", ["group_id"])
  op.create_index(
    "ix_ticket_work_items_assignee_user_id",
    "ticket_work_items",
    ["assignee_user_id"],
  )
