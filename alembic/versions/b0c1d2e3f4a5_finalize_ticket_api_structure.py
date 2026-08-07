"""Finalize simplified ticket naming.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op


revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
  """Rename workflow ownership columns to their final concise names."""

  op.alter_column(
    "tickets",
    "current_responsible_user_id",
    new_column_name="current_assignee_id",
  )
  op.execute(
    "ALTER INDEX ix_tickets_current_responsible_user_id "
    "RENAME TO ix_tickets_current_assignee_id"
  )
  op.execute(
    "ALTER TABLE tickets RENAME CONSTRAINT "
    "tickets_current_responsible_user_id_fkey "
    "TO tickets_current_assignee_id_fkey"
  )

  op.alter_column(
    "tickets",
    "pending_return_to_user_id",
    new_column_name="return_to_user_id",
  )
  op.execute(
    "ALTER INDEX ix_tickets_pending_return_to_user_id "
    "RENAME TO ix_tickets_return_to_user_id"
  )
  op.execute(
    "ALTER TABLE tickets RENAME CONSTRAINT "
    "fk_tickets_pending_return_to_user_id_users "
    "TO fk_tickets_return_to_user_id_users"
  )


def downgrade() -> None:
  """Restore the former verbose workflow ownership column names."""

  op.execute(
    "ALTER TABLE tickets RENAME CONSTRAINT "
    "fk_tickets_return_to_user_id_users "
    "TO fk_tickets_pending_return_to_user_id_users"
  )
  op.execute(
    "ALTER INDEX ix_tickets_return_to_user_id "
    "RENAME TO ix_tickets_pending_return_to_user_id"
  )
  op.alter_column(
    "tickets",
    "return_to_user_id",
    new_column_name="pending_return_to_user_id",
  )

  op.execute(
    "ALTER TABLE tickets RENAME CONSTRAINT "
    "tickets_current_assignee_id_fkey "
    "TO tickets_current_responsible_user_id_fkey"
  )
  op.execute(
    "ALTER INDEX ix_tickets_current_assignee_id "
    "RENAME TO ix_tickets_current_responsible_user_id"
  )
  op.alter_column(
    "tickets",
    "current_assignee_id",
    new_column_name="current_responsible_user_id",
  )
