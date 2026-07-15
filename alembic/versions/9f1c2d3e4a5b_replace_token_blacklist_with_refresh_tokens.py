"""Replace raw JWT blacklist with hashed refresh tokens.

Revision ID: 9f1c2d3e4a5b
Revises: 65ec6cbfc19c
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f1c2d3e4a5b"
down_revision: Union[str, Sequence[str], None] = "65ec6cbfc19c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  op.drop_index(
    op.f("ix_blacklisted_tokens_token"),
    table_name="blacklisted_tokens",
  )
  op.drop_table("blacklisted_tokens")

  op.create_table(
    "refresh_tokens",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("user_id", sa.UUID(), nullable=False),
    sa.Column("token_hash", sa.String(length=64), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
    op.f("ix_refresh_tokens_user_id"),
    "refresh_tokens",
    ["user_id"],
    unique=False,
  )
  op.create_index(
    op.f("ix_refresh_tokens_token_hash"),
    "refresh_tokens",
    ["token_hash"],
    unique=True,
  )


def downgrade() -> None:
  op.drop_index(
    op.f("ix_refresh_tokens_token_hash"),
    table_name="refresh_tokens",
  )
  op.drop_index(
    op.f("ix_refresh_tokens_user_id"),
    table_name="refresh_tokens",
  )
  op.drop_table("refresh_tokens")

  op.create_table(
    "blacklisted_tokens",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("token", sa.String(), nullable=False),
    sa.Column("blacklisted_on", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
    op.f("ix_blacklisted_tokens_token"),
    "blacklisted_tokens",
    ["token"],
    unique=True,
  )
