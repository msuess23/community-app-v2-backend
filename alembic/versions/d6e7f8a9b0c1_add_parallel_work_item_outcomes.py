"""Add projected outcomes and group uniqueness for ticket work items.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORK_ITEM_OUTCOMES = ("APPROVED", "REJECTED", "ACKNOWLEDGED")


def upgrade() -> None:
  """Extends the task projection without changing the immutable event format."""

  op.add_column(
    "ticket_work_items",
    sa.Column("outcome", sa.String(length=16), nullable=True),
  )
  op.create_check_constraint(
    "ck_ticket_work_items_outcome",
    "ticket_work_items",
    "outcome IS NULL OR outcome IN ('APPROVED', 'REJECTED', 'ACKNOWLEDGED')",
  )
  op.create_unique_constraint(
    "uq_ticket_work_items_group_assignee",
    "ticket_work_items",
    ["ticket_id", "group_id", "assignee_user_id"],
  )


def downgrade() -> None:
  """Removes the additional work-item projection fields and constraint."""

  op.drop_constraint(
    "uq_ticket_work_items_group_assignee",
    "ticket_work_items",
    type_="unique",
  )
  op.drop_constraint(
    "ck_ticket_work_items_outcome",
    "ticket_work_items",
    type_="check",
  )
  op.drop_column("ticket_work_items", "outcome")
