"""harden password reset challenges

Revision ID: d4a6f9c1b2e7
Revises: 9b7d3e8a2c41
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4a6f9c1b2e7"
down_revision: Union[str, Sequence[str], None] = "9b7d3e8a2c41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # Reset challenges are deliberately short-lived credentials. Invalidating
  # outstanding challenges is safer and simpler than attempting to migrate
  # them from their email-based representation while the table is changing.
  op.execute(sa.text("DELETE FROM password_resets"))

  op.drop_index(
    op.f("ix_password_resets_email"),
    table_name="password_resets",
  )
  op.drop_column("password_resets", "email")

  op.add_column(
    "password_resets",
    sa.Column("user_id", sa.UUID(), nullable=False),
  )
  op.add_column(
    "password_resets",
    sa.Column(
      "failed_attempts",
      sa.Integer(),
      server_default="0",
      nullable=False,
    ),
  )
  op.alter_column(
    "password_resets",
    "created_at",
    new_column_name="requested_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
    server_default=sa.text("now()"),
  )

  op.create_foreign_key(
    "fk_password_resets_user_id_users",
    "password_resets",
    "users",
    ["user_id"],
    ["id"],
    ondelete="CASCADE",
  )
  op.create_unique_constraint(
    "uq_password_resets_user_id",
    "password_resets",
    ["user_id"],
  )
  op.create_check_constraint(
    "ck_password_resets_failed_attempts_nonnegative",
    "password_resets",
    "failed_attempts >= 0",
  )
  op.create_index(
    op.f("ix_password_resets_expires_at"),
    "password_resets",
    ["expires_at"],
    unique=False,
  )


def downgrade() -> None:
  # The old representation cannot safely reconstruct active challenges. Keep
  # the same security property as upgrade and invalidate all outstanding OTPs.
  op.execute(sa.text("DELETE FROM password_resets"))

  op.drop_index(
    op.f("ix_password_resets_expires_at"),
    table_name="password_resets",
  )
  op.drop_constraint(
    "ck_password_resets_failed_attempts_nonnegative",
    "password_resets",
    type_="check",
  )
  op.drop_constraint(
    "uq_password_resets_user_id",
    "password_resets",
    type_="unique",
  )
  op.drop_constraint(
    "fk_password_resets_user_id_users",
    "password_resets",
    type_="foreignkey",
  )

  op.alter_column(
    "password_resets",
    "requested_at",
    new_column_name="created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=True,
    server_default=None,
  )
  op.drop_column("password_resets", "failed_attempts")
  op.drop_column("password_resets", "user_id")
  op.add_column(
    "password_resets",
    sa.Column("email", sa.String(), nullable=False),
  )
  op.create_index(
    op.f("ix_password_resets_email"),
    "password_resets",
    ["email"],
    unique=False,
  )
