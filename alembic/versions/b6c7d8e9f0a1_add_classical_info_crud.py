"""Add classical mutable Info CRUD and owned status history.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INFO_CATEGORIES = (
  "EVENT",
  "CONSTRUCTION",
  "MAINTENANCE",
  "ANNOUNCEMENT",
  "OTHER",
)
_INFO_STATUSES = ("SCHEDULED", "ACTIVE", "DONE", "CANCELLED")


def _check(column: str, values: tuple[str, ...]) -> str:
  return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Create mutable Infos and status rows that cascade on physical deletion."""

  op.create_table(
    "infos",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("title", sa.String(length=255), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column("category", sa.String(length=32), nullable=False),
    sa.Column("office_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("address_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("current_status", sa.String(length=16), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("ends_at > starts_at", name="ck_infos_time_order"),
    sa.CheckConstraint(
      _check("category", _INFO_CATEGORIES),
      name="ck_infos_category",
    ),
    sa.CheckConstraint(
      _check("current_status", _INFO_STATUSES),
      name="ck_infos_current_status",
    ),
    sa.ForeignKeyConstraint(["address_id"], ["addresses.id"]),
    sa.ForeignKeyConstraint(
      ["office_id"],
      ["offices.id"],
      ondelete="SET NULL",
    ),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("address_id", name="uq_infos_address_id"),
  )
  op.create_index("ix_infos_category", "infos", ["category"])
  op.create_index("ix_infos_created_at", "infos", ["created_at"])
  op.create_index("ix_infos_current_status", "infos", ["current_status"])
  op.create_index("ix_infos_ends_at", "infos", ["ends_at"])
  op.create_index("ix_infos_office_id", "infos", ["office_id"])
  op.create_index("ix_infos_starts_at", "infos", ["starts_at"])

  op.create_table(
    "info_status_entries",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("info_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("message", sa.String(length=1000), nullable=True),
    sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
      _check("status", _INFO_STATUSES),
      name="ck_info_status_entries_status",
    ),
    sa.ForeignKeyConstraint(
      ["info_id"],
      ["infos.id"],
      ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    sa.PrimaryKeyConstraint("id"),
  )
  op.create_index(
    "ix_info_status_entries_created_at",
    "info_status_entries",
    ["created_at"],
  )
  op.create_index(
    "ix_info_status_entries_created_by_user_id",
    "info_status_entries",
    ["created_by_user_id"],
  )
  op.create_index(
    "ix_info_status_entries_info_id",
    "info_status_entries",
    ["info_id"],
  )
  op.create_index(
    "ix_info_status_entries_status",
    "info_status_entries",
    ["status"],
  )


def downgrade() -> None:
  """Remove status history and mutable Info rows."""

  op.drop_index(
    "ix_info_status_entries_status",
    table_name="info_status_entries",
  )
  op.drop_index(
    "ix_info_status_entries_info_id",
    table_name="info_status_entries",
  )
  op.drop_index(
    "ix_info_status_entries_created_by_user_id",
    table_name="info_status_entries",
  )
  op.drop_index(
    "ix_info_status_entries_created_at",
    table_name="info_status_entries",
  )
  op.drop_table("info_status_entries")

  op.drop_index("ix_infos_starts_at", table_name="infos")
  op.drop_index("ix_infos_office_id", table_name="infos")
  op.drop_index("ix_infos_ends_at", table_name="infos")
  op.drop_index("ix_infos_current_status", table_name="infos")
  op.drop_index("ix_infos_created_at", table_name="infos")
  op.drop_index("ix_infos_category", table_name="infos")
  op.drop_table("infos")
