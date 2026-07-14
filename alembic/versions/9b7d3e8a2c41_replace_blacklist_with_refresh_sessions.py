"""replace token blacklist with rotating refresh sessions

Revision ID: 9b7d3e8a2c41
Revises: 4f1a2c9d7e30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9b7d3e8a2c41"
down_revision: Union[str, Sequence[str], None] = "4f1a2c9d7e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing refresh tokens predate server-side sessions and cannot be
    # migrated safely. Invalidate all currently issued access/refresh tokens
    # once so every client starts with a session-backed login.
    op.execute(
        sa.text("UPDATE users SET auth_version = auth_version + 1")
    )

    op.drop_index(
        op.f("ix_blacklisted_tokens_token"),
        table_name="blacklisted_tokens",
    )
    op.drop_table("blacklisted_tokens")

    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=32), nullable=True),
        sa.Column("replaced_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            name="fk_refresh_sessions_replaced_by_id_refresh_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_sessions_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_sessions"),
    )
    op.create_index(
        op.f("ix_refresh_sessions_expires_at"),
        "refresh_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_sessions_family_id"),
        "refresh_sessions",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_refresh_sessions_token_hash"),
        "refresh_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_refresh_sessions_user_id"),
        "refresh_sessions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_refresh_sessions_user_id"),
        table_name="refresh_sessions",
    )
    op.drop_index(
        op.f("ix_refresh_sessions_token_hash"),
        table_name="refresh_sessions",
    )
    op.drop_index(
        op.f("ix_refresh_sessions_family_id"),
        table_name="refresh_sessions",
    )
    op.drop_index(
        op.f("ix_refresh_sessions_expires_at"),
        table_name="refresh_sessions",
    )
    op.drop_table("refresh_sessions")

    op.create_table(
        "blacklisted_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("blacklisted_on", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_blacklisted_tokens"),
    )
    op.create_index(
        op.f("ix_blacklisted_tokens_token"),
        "blacklisted_tokens",
        ["token"],
        unique=True,
    )
