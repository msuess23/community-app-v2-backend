"""Harden ticket workflow contract and event-stream retention.

Revision ID: f1a2b3c4d5e6
Revises: e8f9a0b1c2d3
Create Date: 2026-08-05
"""

from collections.abc import Sequence

from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_WORKFLOW_STATES = (
  "NEW",
  "AWAITING_PRIMARY_ASSIGNMENT",
  "RETURNED_TO_DISPATCH",
  "IN_PROGRESS",
  "WAITING_FOR_COSIGNATURE",
  "WAITING_FOR_CITIZEN",
  "WAITING_FOR_DECISION",
  "COMPLETED",
)


def _check(column: str, values: tuple[str, ...]) -> str:
  return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Separate redispatch from new submissions and retain aggregate events."""

  op.drop_constraint("ck_tickets_workflow_state", "tickets", type_="check")
  op.execute(
    "UPDATE tickets SET workflow_state = 'RETURNED_TO_DISPATCH' "
    "WHERE workflow_state = 'NEW' AND public_status = 'IN_PROGRESS'"
  )
  op.create_check_constraint(
    "ck_tickets_workflow_state",
    "tickets",
    _check("workflow_state", _WORKFLOW_STATES),
  )

  op.drop_constraint(
    "ticket_events_ticket_id_fkey",
    "ticket_events",
    type_="foreignkey",
  )
  op.create_foreign_key(
    "ticket_events_ticket_id_fkey",
    "ticket_events",
    "tickets",
    ["ticket_id"],
    ["id"],
    ondelete="RESTRICT",
  )

  op.drop_constraint(
    "appointment_events_appointment_id_fkey",
    "appointment_events",
    type_="foreignkey",
  )
  op.create_foreign_key(
    "appointment_events_appointment_id_fkey",
    "appointment_events",
    "appointments",
    ["appointment_id"],
    ["id"],
    ondelete="RESTRICT",
  )

  op.execute(
    """
    CREATE FUNCTION reject_event_stream_mutation()
    RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'Event streams are append-only';
    END;
    $$ LANGUAGE plpgsql
    """
  )
  for table_name in ("ticket_events", "appointment_events"):
    op.execute(
      f"""
      CREATE TRIGGER trg_{table_name}_append_only
      BEFORE UPDATE OR DELETE ON {table_name}
      FOR EACH ROW EXECUTE FUNCTION reject_event_stream_mutation()
      """
    )


def downgrade() -> None:
  """Restore the former routing state and cascading event foreign keys."""


  for table_name in ("ticket_events", "appointment_events"):
    op.execute(f"DROP TRIGGER trg_{table_name}_append_only ON {table_name}")
  op.execute("DROP FUNCTION reject_event_stream_mutation()")

  op.drop_constraint(
    "appointment_events_appointment_id_fkey",
    "appointment_events",
    type_="foreignkey",
  )
  op.create_foreign_key(
    "appointment_events_appointment_id_fkey",
    "appointment_events",
    "appointments",
    ["appointment_id"],
    ["id"],
    ondelete="CASCADE",
  )

  op.drop_constraint(
    "ticket_events_ticket_id_fkey",
    "ticket_events",
    type_="foreignkey",
  )
  op.create_foreign_key(
    "ticket_events_ticket_id_fkey",
    "ticket_events",
    "tickets",
    ["ticket_id"],
    ["id"],
    ondelete="CASCADE",
  )

  op.drop_constraint("ck_tickets_workflow_state", "tickets", type_="check")
  op.execute(
    "UPDATE tickets SET workflow_state = 'NEW' "
    "WHERE workflow_state = 'RETURNED_TO_DISPATCH'"
  )
  op.create_check_constraint(
    "ck_tickets_workflow_state",
    "tickets",
    _check(
      "workflow_state",
      tuple(value for value in _WORKFLOW_STATES if value != "RETURNED_TO_DISPATCH"),
    ),
  )
