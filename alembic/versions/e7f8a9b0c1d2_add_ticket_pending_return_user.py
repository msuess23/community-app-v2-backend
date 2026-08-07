"""Add the pending workflow return target to ticket projections.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  """Stores return targets and renames the forwarding event constraint value."""

  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
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
    "'TICKET_COMMENTED')",
  )
  op.add_column(
    "tickets",
    sa.Column(
      "pending_return_to_user_id",
      postgresql.UUID(as_uuid=True),
      nullable=True,
    ),
  )
  op.create_foreign_key(
    "fk_tickets_pending_return_to_user_id_users",
    "tickets",
    "users",
    ["pending_return_to_user_id"],
    ["id"],
  )
  op.create_index(
    "ix_tickets_pending_return_to_user_id",
    "tickets",
    ["pending_return_to_user_id"],
  )


def downgrade() -> None:
  """Removes the return target and restores the former event constraint value."""

  op.drop_index("ix_tickets_pending_return_to_user_id", table_name="tickets")
  op.drop_constraint(
    "fk_tickets_pending_return_to_user_id_users",
    "tickets",
    type_="foreignkey",
  )
  op.drop_column("tickets", "pending_return_to_user_id")
  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    "event_type IN ("
    "'TICKET_SUBMITTED', 'TICKET_DETAILS_UPDATED', 'TICKET_CANCELLED', "
    "'TICKET_DISPATCHED', 'PRIMARY_OFFICER_ASSIGNED', "
    "'CURRENT_RESPONSIBLE_CHANGED', 'PARALLEL_WORK_ITEMS_REQUESTED', "
    "'WORK_ITEM_COMPLETED', 'WORK_ITEM_CANCELLED', "
    "'CITIZEN_RESPONSE_REQUESTED', 'CITIZEN_RESPONDED', "
    "'TICKET_ESCALATED', 'ESCALATION_APPROVED', 'ESCALATION_REJECTED', "
    "'TICKET_RESOLVED', 'TICKET_REJECTED', 'TICKET_COMMENTED')",
  )
