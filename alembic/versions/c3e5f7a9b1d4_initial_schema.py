"""initial schema

Revision ID: c3e5f7a9b1d4
Revises: None

This project has no production data. The previous development-only migration
chain was therefore squashed into this single baseline migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c3e5f7a9b1d4"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


role_enum = postgresql.ENUM(
  "CITIZEN",
  "DISPATCHER",
  "OFFICER",
  "MANAGER",
  "ADMIN",
  name="role",
  create_type=False,
)


def upgrade() -> None:
  role_enum.create(op.get_bind(), checkfirst=True)

  op.create_table(
    "addresses",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("street", sa.String(length=150), nullable=False),
    sa.Column("house_number", sa.String(length=20), nullable=False),
    sa.Column("zip_code", sa.String(length=20), nullable=False),
    sa.Column("city", sa.String(length=100), nullable=False),
    sa.Column("latitude", sa.Float(), nullable=True),
    sa.Column("longitude", sa.Float(), nullable=True),
    sa.Column(
      "created_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.Column(
      "updated_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.CheckConstraint(
      "btrim(street) <> ''",
      name="ck_addresses_street_not_blank",
    ),
    sa.CheckConstraint(
      "btrim(house_number) <> ''",
      name="ck_addresses_house_number_not_blank",
    ),
    sa.CheckConstraint(
      "btrim(zip_code) <> ''",
      name="ck_addresses_zip_code_not_blank",
    ),
    sa.CheckConstraint(
      "btrim(city) <> ''",
      name="ck_addresses_city_not_blank",
    ),
    sa.CheckConstraint(
      "(latitude IS NULL AND longitude IS NULL) OR "
      "(latitude IS NOT NULL AND longitude IS NOT NULL)",
      name="ck_addresses_coordinates_complete",
    ),
    sa.CheckConstraint(
      "latitude IS NULL OR latitude BETWEEN -90 AND 90",
      name="ck_addresses_latitude_range",
    ),
    sa.CheckConstraint(
      "longitude IS NULL OR longitude BETWEEN -180 AND 180",
      name="ck_addresses_longitude_range",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_addresses"),
  )

  op.create_table(
    "offices",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("name", sa.String(length=150), nullable=False),
    sa.Column("description", sa.String(length=500), nullable=True),
    sa.Column("contact_email", sa.String(length=320), nullable=True),
    sa.Column("phone", sa.String(length=50), nullable=True),
    sa.Column(
      "services",
      postgresql.ARRAY(sa.String()),
      server_default=sa.text("'{}'::character varying[]"),
      nullable=False,
    ),
    sa.Column(
      "opening_hours",
      postgresql.JSONB(astext_type=sa.Text()),
      server_default=sa.text("'{}'::jsonb"),
      nullable=False,
    ),
    sa.Column(
      "is_active",
      sa.Boolean(),
      server_default=sa.text("true"),
      nullable=False,
    ),
    sa.Column(
      "created_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.Column(
      "updated_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("address_id", sa.UUID(), nullable=True),
    sa.CheckConstraint(
      "btrim(name) <> ''",
      name="ck_offices_name_not_blank",
    ),
    sa.CheckConstraint("name = btrim(name)", name="ck_offices_name_trimmed"),
    sa.CheckConstraint(
      "contact_email IS NULL OR "
      "(contact_email = lower(btrim(contact_email)) AND contact_email <> '')",
      name="ck_offices_contact_email_canonical",
    ),
    sa.CheckConstraint(
      "updated_at >= created_at",
      name="ck_offices_updated_after_creation",
    ),
    sa.CheckConstraint(
      "(is_active IS TRUE AND deactivated_at IS NULL) OR "
      "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
      name="ck_offices_deactivation_state",
    ),
    sa.CheckConstraint(
      "cardinality(services) <= 50",
      name="ck_offices_services_max_items",
    ),
    sa.CheckConstraint(
      "jsonb_typeof(opening_hours) = 'object'",
      name="ck_offices_opening_hours_object",
    ),
    sa.ForeignKeyConstraint(
      ["address_id"],
      ["addresses.id"],
      name="fk_offices_address_id_addresses",
      ondelete="RESTRICT",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_offices"),
    sa.UniqueConstraint("address_id", name="uq_offices_address_id"),
  )
  op.create_index(
    "uq_offices_active_name_ci",
    "offices",
    [sa.literal_column("lower(name)")],
    unique=True,
    postgresql_where=sa.text("is_active IS TRUE"),
  )

  op.create_table(
    "users",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("email", sa.String(length=320), nullable=False),
    sa.Column("hashed_password", sa.String(), nullable=False),
    sa.Column("first_name", sa.String(length=100), nullable=False),
    sa.Column("last_name", sa.String(length=100), nullable=False),
    sa.Column(
      "role",
      role_enum,
      server_default=sa.text("'CITIZEN'::role"),
      nullable=False,
    ),
    sa.Column("office_id", sa.UUID(), nullable=True),
    sa.Column(
      "is_active",
      sa.Boolean(),
      server_default=sa.text("true"),
      nullable=False,
    ),
    sa.Column(
      "auth_version",
      sa.Integer(),
      server_default=sa.text("0"),
      nullable=False,
    ),
    sa.Column(
      "created_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.Column(
      "updated_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
      "btrim(first_name) <> ''",
      name="ck_users_first_name_not_blank",
    ),
    sa.CheckConstraint(
      "email = lower(btrim(email)) AND email <> ''",
      name="ck_users_email_canonical",
    ),
    sa.CheckConstraint(
      "btrim(hashed_password) <> ''",
      name="ck_users_hashed_password_not_blank",
    ),
    sa.CheckConstraint(
      "auth_version >= 0",
      name="ck_users_auth_version_nonnegative",
    ),
    sa.CheckConstraint(
      "updated_at >= created_at",
      name="ck_users_updated_after_creation",
    ),
    sa.CheckConstraint(
      "(is_active IS TRUE AND deactivated_at IS NULL) OR "
      "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
      name="ck_users_deactivation_state",
    ),
    sa.CheckConstraint(
      "btrim(last_name) <> ''",
      name="ck_users_last_name_not_blank",
    ),
    sa.CheckConstraint(
      "((role IN ('CITIZEN', 'ADMIN') AND office_id IS NULL) OR "
      "(role IN ('DISPATCHER', 'OFFICER', 'MANAGER') AND office_id IS NOT NULL))",
      name="ck_users_role_office_assignment",
    ),
    sa.ForeignKeyConstraint(
      ["office_id"],
      ["offices.id"],
      name="fk_users_office_id_offices",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_users"),
  )
  op.create_index(
    "uq_users_email_ci",
    "users",
    [sa.literal_column("lower(email)")],
    unique=True,
  )

  op.create_table(
    "user_history",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("user_id", sa.UUID(), nullable=False),
    sa.Column("email", sa.String(length=320), nullable=False),
    sa.Column("first_name", sa.String(length=100), nullable=False),
    sa.Column("last_name", sa.String(length=100), nullable=False),
    sa.Column("role", role_enum, nullable=False),
    sa.Column("office_id", sa.UUID(), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
    sa.Column("changed_by_user_id", sa.UUID(), nullable=False),
    sa.Column("change_reason", sa.String(length=500), nullable=False),
    sa.CheckConstraint(
      "email <> ''",
      name="ck_user_history_email_not_blank",
    ),
    sa.CheckConstraint(
      "btrim(first_name) <> ''",
      name="ck_user_history_first_name_not_blank",
    ),
    sa.CheckConstraint(
      "btrim(last_name) <> ''",
      name="ck_user_history_last_name_not_blank",
    ),
    sa.CheckConstraint(
      "btrim(change_reason) <> ''",
      name="ck_user_history_change_reason_not_blank",
    ),
    sa.CheckConstraint(
      "(is_active IS TRUE AND deactivated_at IS NULL) OR "
      "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
      name="ck_user_history_deactivation_state",
    ),
    sa.CheckConstraint(
      "valid_to >= valid_from",
      name="ck_user_history_valid_period",
    ),
    sa.ForeignKeyConstraint(
      ["changed_by_user_id"],
      ["users.id"],
      name="fk_user_history_changed_by_user_id_users",
      ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
      ["office_id"],
      ["offices.id"],
      name="fk_user_history_office_id_offices",
      ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
      ["user_id"],
      ["users.id"],
      name="fk_user_history_user_id_users",
      ondelete="RESTRICT",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_user_history"),
  )
  op.create_index("ix_user_history_user_id", "user_history", ["user_id"])

  op.create_table(
    "office_history",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("office_id", sa.UUID(), nullable=False),
    sa.Column("name", sa.String(length=150), nullable=False),
    sa.Column("description", sa.String(length=500), nullable=True),
    sa.Column("contact_email", sa.String(length=320), nullable=True),
    sa.Column("phone", sa.String(length=50), nullable=True),
    sa.Column(
      "services",
      postgresql.ARRAY(sa.String()),
      server_default=sa.text("'{}'::character varying[]"),
      nullable=False,
    ),
    sa.Column(
      "opening_hours",
      postgresql.JSONB(astext_type=sa.Text()),
      server_default=sa.text("'{}'::jsonb"),
      nullable=False,
    ),
    sa.Column("address_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("is_active", sa.Boolean(), nullable=False),
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
    sa.Column("changed_by_user_id", sa.UUID(), nullable=False),
    sa.Column("change_reason", sa.String(length=500), nullable=False),
    sa.CheckConstraint(
      "btrim(name) <> ''",
      name="ck_office_history_name_not_blank",
    ),
    sa.CheckConstraint(
      "cardinality(services) <= 50",
      name="ck_office_history_services_max_items",
    ),
    sa.CheckConstraint(
      "btrim(change_reason) <> ''",
      name="ck_office_history_change_reason_not_blank",
    ),
    sa.CheckConstraint(
      "(is_active IS TRUE AND deactivated_at IS NULL) OR "
      "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
      name="ck_office_history_deactivation_state",
    ),
    sa.CheckConstraint(
      "jsonb_typeof(opening_hours) = 'object'",
      name="ck_office_history_opening_hours_object",
    ),
    sa.CheckConstraint(
      "valid_to >= valid_from",
      name="ck_office_history_valid_period",
    ),
    sa.ForeignKeyConstraint(
      ["changed_by_user_id"],
      ["users.id"],
      name="fk_office_history_changed_by_user_id_users",
      ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
      ["office_id"],
      ["offices.id"],
      name="fk_office_history_office_id_offices",
      ondelete="RESTRICT",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_office_history"),
  )
  op.create_index("ix_office_history_office_id", "office_history", ["office_id"])

  op.create_table(
    "password_resets",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("user_id", sa.UUID(), nullable=False),
    sa.Column("otp_hash", sa.String(), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
      "requested_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.CheckConstraint(
      "btrim(otp_hash) <> ''",
      name="ck_password_resets_otp_hash_not_blank",
    ),
    sa.CheckConstraint(
      "expires_at > requested_at",
      name="ck_password_resets_expiry_after_request",
    ),
    sa.ForeignKeyConstraint(
      ["user_id"],
      ["users.id"],
      name="fk_password_resets_user_id_users",
      ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_password_resets"),
    sa.UniqueConstraint("user_id", name="uq_password_resets_user_id"),
  )
  op.create_index("ix_password_resets_expires_at", "password_resets", ["expires_at"])

  op.create_table(
    "refresh_sessions",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("user_id", sa.UUID(), nullable=False),
    sa.Column("token_hash", sa.String(length=64), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column(
      "created_at",
      sa.DateTime(timezone=True),
      server_default=sa.text("now()"),
      nullable=False,
    ),
    sa.CheckConstraint(
      "length(token_hash) = 64",
      name="ck_refresh_sessions_token_hash_length",
    ),
    sa.CheckConstraint(
      "expires_at > created_at",
      name="ck_refresh_sessions_expiry_after_creation",
    ),
    sa.ForeignKeyConstraint(
      ["user_id"],
      ["users.id"],
      name="fk_refresh_sessions_user_id_users",
      ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("id", name="pk_refresh_sessions"),
  )
  op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])
  op.create_index(
    "ix_refresh_sessions_token_hash",
    "refresh_sessions",
    ["token_hash"],
    unique=True,
  )
  op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])


def downgrade() -> None:
  op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
  op.drop_index("ix_refresh_sessions_token_hash", table_name="refresh_sessions")
  op.drop_index("ix_refresh_sessions_expires_at", table_name="refresh_sessions")
  op.drop_table("refresh_sessions")

  op.drop_index("ix_password_resets_expires_at", table_name="password_resets")
  op.drop_table("password_resets")

  op.drop_index("ix_office_history_office_id", table_name="office_history")
  op.drop_table("office_history")

  op.drop_index("ix_user_history_user_id", table_name="user_history")
  op.drop_table("user_history")

  op.drop_index("uq_users_email_ci", table_name="users")
  op.drop_table("users")

  op.drop_index("uq_offices_active_name_ci", table_name="offices")
  op.drop_table("offices")
  op.drop_table("addresses")

  role_enum.drop(op.get_bind(), checkfirst=True)
