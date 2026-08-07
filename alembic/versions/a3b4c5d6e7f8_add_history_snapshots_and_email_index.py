"""Add complete history snapshots and case-insensitive user emails.

Revision ID: a3b4c5d6e7f8
Revises: 9f1c2d3e4a5b
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "9f1c2d3e4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.add_column(
    "user_history",
    sa.Column("office_id", sa.UUID(), nullable=True),
  )
  op.create_foreign_key(
    "fk_user_history_office_id_offices",
    "user_history",
    "offices",
    ["office_id"],
    ["id"],
  )
  op.add_column(
    "user_history",
    sa.Column(
      "is_active",
      sa.Boolean(),
      nullable=False,
      server_default=sa.true(),
    ),
  )
  op.add_column(
    "user_history",
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
  )
  op.add_column(
    "office_history",
    sa.Column(
      "is_active",
      sa.Boolean(),
      nullable=False,
      server_default=sa.true(),
    ),
  )

  # All application writes already normalize email addresses. Normalize existing
  # development data before enforcing the same rule in PostgreSQL.
  op.execute("UPDATE users SET email = lower(trim(email))")
  op.execute(
    "CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))"
  )


def downgrade() -> None:
  op.drop_index("uq_users_email_lower", table_name="users")
  op.drop_column("office_history", "is_active")
  op.drop_column("user_history", "deactivated_at")
  op.drop_column("user_history", "is_active")
  op.drop_constraint(
    "fk_user_history_office_id_offices",
    "user_history",
    type_="foreignkey",
  )
  op.drop_column("user_history", "office_id")
