"""Align history snapshots and ORM-required columns.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
  """Backfill legacy nulls, add audit FKs and store structured addresses."""

  op.execute("UPDATE users SET role = 'CITIZEN' WHERE role IS NULL")
  op.execute("UPDATE users SET is_active = true WHERE is_active IS NULL")
  op.execute("UPDATE users SET created_at = now() WHERE created_at IS NULL")

  op.execute("UPDATE offices SET services = '{}' WHERE services IS NULL")
  op.execute("UPDATE offices SET opening_hours = '{}'::jsonb WHERE opening_hours IS NULL")
  op.execute("UPDATE offices SET is_active = true WHERE is_active IS NULL")
  op.execute("UPDATE offices SET created_at = now() WHERE created_at IS NULL")

  op.execute("UPDATE addresses SET created_at = now() WHERE created_at IS NULL")
  op.execute("UPDATE addresses SET updated_at = created_at WHERE updated_at IS NULL")

  op.execute("UPDATE user_history SET changed_by_user_id = user_id WHERE changed_by_user_id IS NULL")
  op.execute("UPDATE user_history SET email = '' WHERE email IS NULL")
  op.execute("UPDATE user_history SET first_name = '' WHERE first_name IS NULL")
  op.execute("UPDATE user_history SET last_name = '' WHERE last_name IS NULL")
  op.execute("UPDATE user_history SET role = 'CITIZEN' WHERE role IS NULL")
  op.execute("UPDATE user_history SET changed_at = now() WHERE changed_at IS NULL")

  op.execute(
    "UPDATE office_history SET changed_by_user_id = "
    "(SELECT id FROM users ORDER BY created_at, id LIMIT 1) "
    "WHERE changed_by_user_id IS NULL"
  )
  op.execute("UPDATE office_history SET name = '' WHERE name IS NULL")
  op.execute("UPDATE office_history SET services = '{}' WHERE services IS NULL")
  op.execute(
    "UPDATE office_history SET opening_hours = '{}'::jsonb "
    "WHERE opening_hours IS NULL"
  )
  op.execute("UPDATE office_history SET changed_at = now() WHERE changed_at IS NULL")

  for table, column in (
    ("users", "role"),
    ("users", "is_active"),
    ("users", "created_at"),
    ("offices", "services"),
    ("offices", "opening_hours"),
    ("offices", "is_active"),
    ("offices", "created_at"),
    ("addresses", "created_at"),
    ("addresses", "updated_at"),
    ("user_history", "user_id"),
    ("user_history", "email"),
    ("user_history", "first_name"),
    ("user_history", "last_name"),
    ("user_history", "role"),
    ("user_history", "changed_at"),
    ("user_history", "changed_by_user_id"),
    ("office_history", "office_id"),
    ("office_history", "name"),
    ("office_history", "services"),
    ("office_history", "opening_hours"),
    ("office_history", "changed_at"),
    ("office_history", "changed_by_user_id"),
  ):
    op.alter_column(table, column, nullable=False)

  # Email normalization plus uq_users_email_lower provide the actual
  # case-insensitive uniqueness rule. Keep the plain index non-unique.
  op.drop_index("ix_users_email", table_name="users")
  op.create_index("ix_users_email", "users", ["email"], unique=False)

  op.create_foreign_key(
    "fk_user_history_changed_by_user_id_users",
    "user_history",
    "users",
    ["changed_by_user_id"],
    ["id"],
  )
  op.create_foreign_key(
    "fk_office_history_changed_by_user_id_users",
    "office_history",
    "users",
    ["changed_by_user_id"],
    ["id"],
  )

  op.alter_column(
    "office_history",
    "address_snapshot",
    type_=postgresql.JSONB(astext_type=sa.Text()),
    postgresql_using=(
      "CASE WHEN address_snapshot IS NULL THEN NULL "
      "ELSE jsonb_build_object('formatted', address_snapshot) END"
    ),
  )


def downgrade() -> None:
  """Restore legacy nullable columns and formatted address snapshots."""

  op.alter_column(
    "office_history",
    "address_snapshot",
    type_=sa.String(),
    postgresql_using=(
      "CASE WHEN address_snapshot IS NULL THEN NULL "
      "ELSE COALESCE(address_snapshot->>'formatted', "
      "concat_ws(', ', concat_ws(' ', address_snapshot->>'street', "
      "address_snapshot->>'house_number'), concat_ws(' ', "
      "address_snapshot->>'zip_code', address_snapshot->>'city'))) END"
    ),
  )

  op.drop_index("ix_users_email", table_name="users")
  op.create_index("ix_users_email", "users", ["email"], unique=True)

  op.drop_constraint(
    "fk_office_history_changed_by_user_id_users",
    "office_history",
    type_="foreignkey",
  )
  op.drop_constraint(
    "fk_user_history_changed_by_user_id_users",
    "user_history",
    type_="foreignkey",
  )

  for table, column in (
    ("office_history", "changed_by_user_id"),
    ("office_history", "changed_at"),
    ("office_history", "opening_hours"),
    ("office_history", "services"),
    ("office_history", "name"),
    ("office_history", "office_id"),
    ("user_history", "changed_by_user_id"),
    ("user_history", "changed_at"),
    ("user_history", "role"),
    ("user_history", "last_name"),
    ("user_history", "first_name"),
    ("user_history", "email"),
    ("user_history", "user_id"),
    ("addresses", "updated_at"),
    ("addresses", "created_at"),
    ("offices", "created_at"),
    ("offices", "is_active"),
    ("offices", "opening_hours"),
    ("offices", "services"),
    ("users", "created_at"),
    ("users", "is_active"),
    ("users", "role"),
  ):
    op.alter_column(table, column, nullable=True)
