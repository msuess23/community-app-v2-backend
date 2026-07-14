"""database history and migration hardening

Revision ID: a1c3e5f7b9d2
Revises: f8d0b3c5a7e9
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, Sequence[str], None] = "f8d0b3c5a7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
  _prepare_existing_data()
  _align_column_types()
  _add_server_defaults_and_nullability()
  _add_domain_constraints()
  _add_anonymization_audit_fields()
  _install_history_guards()


def _prepare_existing_data() -> None:
  op.execute("UPDATE users SET email = lower(btrim(email))")
  op.execute("UPDATE offices SET name = btrim(name)")
  op.execute(
    "UPDATE offices SET contact_email = lower(btrim(contact_email)) "
    "WHERE contact_email IS NOT NULL"
  )

  op.execute("UPDATE users SET created_at = now() WHERE created_at IS NULL")
  op.execute("UPDATE offices SET created_at = now() WHERE created_at IS NULL")
  op.execute("UPDATE addresses SET created_at = now() WHERE created_at IS NULL")
  op.execute(
    "UPDATE addresses SET updated_at = COALESCE(updated_at, created_at, now()) "
    "WHERE updated_at IS NULL"
  )

  # Preserve audit metadata for rows anonymized by the legacy bulk update.
  op.add_column(
    "user_history",
    sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
  )
  op.add_column(
    "user_history",
    sa.Column("anonymized_by_user_id", sa.UUID(), nullable=True),
  )
  op.add_column(
    "user_history",
    sa.Column("anonymization_reason", sa.String(length=500), nullable=True),
  )
  op.execute(
    sa.text(
      """
      UPDATE user_history
      SET anonymized_at = COALESCE(valid_to, valid_from, now()),
          anonymized_by_user_id = CAST(:system_user_id AS uuid),
          anonymization_reason = 'Legacy anonymization backfilled by migration'
      WHERE email = 'deleted@local.com'
        AND first_name = 'gelöschter'
        AND last_name = 'Nutzer'
      """
    ).bindparams(system_user_id=SYSTEM_USER_ID)
  )

  op.execute(
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM users
        WHERE email = '' OR email <> lower(btrim(email))
           OR btrim(hashed_password) = ''
           OR auth_version < 0
           OR (is_active IS TRUE AND deactivated_at IS NOT NULL)
           OR (is_active IS FALSE AND deactivated_at IS NULL)
      ) THEN
        RAISE EXCEPTION 'Users violate canonical identity or lifecycle constraints';
      END IF;

      IF EXISTS (
        SELECT 1 FROM offices
        WHERE name = '' OR name <> btrim(name)
           OR (contact_email IS NOT NULL AND (
             contact_email = '' OR contact_email <> lower(btrim(contact_email))
           ))
           OR (is_active IS TRUE AND deactivated_at IS NOT NULL)
           OR (is_active IS FALSE AND deactivated_at IS NULL)
      ) THEN
        RAISE EXCEPTION 'Offices violate canonical identity or lifecycle constraints';
      END IF;

      IF EXISTS (
        SELECT 1 FROM addresses
        WHERE (latitude IS NULL) <> (longitude IS NULL)
           OR latitude NOT BETWEEN -90 AND 90
           OR longitude NOT BETWEEN -180 AND 180
      ) THEN
        RAISE EXCEPTION 'Addresses contain incomplete or out-of-range coordinates';
      END IF;

      IF EXISTS (
        SELECT 1 FROM password_resets
        WHERE btrim(otp_hash) = '' OR expires_at <= requested_at
      ) THEN
        RAISE EXCEPTION 'Password reset rows violate expiry constraints';
      END IF;

      IF EXISTS (
        SELECT 1 FROM refresh_sessions
        WHERE length(token_hash) <> 64
           OR expires_at <= created_at
           OR ((revoked_at IS NULL) <> (revoke_reason IS NULL))
           OR (revoke_reason IS NOT NULL AND btrim(revoke_reason) = '')
      ) THEN
        RAISE EXCEPTION 'Refresh sessions violate token or revocation constraints';
      END IF;
    END
    $$;
    """
  )



def _align_column_types() -> None:
  for table_name, column_name, length, nullable in (
    ("users", "email", 320, False),
    ("user_history", "email", 320, False),
    ("user_history", "change_reason", 500, False),
    ("offices", "name", 150, False),
    ("offices", "description", 500, True),
    ("offices", "contact_email", 320, True),
    ("offices", "phone", 50, True),
    ("office_history", "name", 150, False),
    ("office_history", "description", 500, True),
    ("office_history", "contact_email", 320, True),
    ("office_history", "phone", 50, True),
    ("office_history", "change_reason", 500, False),
  ):
    op.alter_column(
      table_name,
      column_name,
      existing_type=sa.String(),
      type_=sa.String(length=length),
      existing_nullable=nullable,
    )

def _add_server_defaults_and_nullability() -> None:
  op.alter_column(
    "users",
    "role",
    existing_type=sa.Enum(name="role"),
    existing_nullable=False,
    server_default=sa.text("'CITIZEN'::role"),
  )
  op.alter_column(
    "users",
    "is_active",
    existing_type=sa.Boolean(),
    existing_nullable=False,
    server_default=sa.text("true"),
  )
  op.alter_column(
    "offices",
    "is_active",
    existing_type=sa.Boolean(),
    existing_nullable=False,
    server_default=sa.text("true"),
  )
  op.alter_column(
    "offices",
    "services",
    existing_type=sa.ARRAY(sa.String()),
    existing_nullable=False,
    server_default=sa.text("'{}'::character varying[]"),
  )
  op.alter_column(
    "offices",
    "opening_hours",
    existing_type=postgresql.JSONB(),
    existing_nullable=False,
    server_default=sa.text("'{}'::jsonb"),
  )
  op.alter_column(
    "users",
    "created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
    server_default=sa.text("now()"),
  )
  op.alter_column(
    "offices",
    "created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
    server_default=sa.text("now()"),
  )
  op.alter_column(
    "addresses",
    "created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
    server_default=sa.text("now()"),
  )
  op.alter_column(
    "addresses",
    "updated_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
    server_default=sa.text("now()"),
  )
  op.alter_column(
    "user_history",
    "valid_from",
    existing_type=sa.DateTime(timezone=True),
    existing_nullable=False,
    server_default=sa.text("now()"),
  )
  op.alter_column(
    "office_history",
    "valid_from",
    existing_type=sa.DateTime(timezone=True),
    existing_nullable=False,
    server_default=sa.text("now()"),
  )
  op.alter_column(
    "office_history",
    "services",
    existing_type=sa.ARRAY(sa.String()),
    existing_nullable=False,
    server_default=sa.text("'{}'::character varying[]"),
  )
  op.alter_column(
    "office_history",
    "opening_hours",
    existing_type=postgresql.JSONB(),
    existing_nullable=False,
    server_default=sa.text("'{}'::jsonb"),
  )


def _add_domain_constraints() -> None:
  op.create_check_constraint(
    "ck_users_email_canonical",
    "users",
    "email = lower(btrim(email)) AND email <> ''",
  )
  op.create_check_constraint(
    "ck_users_hashed_password_not_blank",
    "users",
    "btrim(hashed_password) <> ''",
  )
  op.create_check_constraint(
    "ck_users_auth_version_nonnegative",
    "users",
    "auth_version >= 0",
  )
  op.create_check_constraint(
    "ck_users_deactivation_state",
    "users",
    "(is_active IS TRUE AND deactivated_at IS NULL) OR "
    "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
  )

  op.create_check_constraint(
    "ck_offices_name_trimmed",
    "offices",
    "name = btrim(name)",
  )
  op.create_check_constraint(
    "ck_offices_contact_email_canonical",
    "offices",
    "contact_email IS NULL OR "
    "(contact_email = lower(btrim(contact_email)) AND contact_email <> '')",
  )
  op.create_check_constraint(
    "ck_offices_deactivation_state",
    "offices",
    "(is_active IS TRUE AND deactivated_at IS NULL) OR "
    "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
  )

  op.create_check_constraint(
    "ck_addresses_coordinates_complete",
    "addresses",
    "(latitude IS NULL AND longitude IS NULL) OR "
    "(latitude IS NOT NULL AND longitude IS NOT NULL)",
  )
  op.create_check_constraint(
    "ck_addresses_latitude_range",
    "addresses",
    "latitude IS NULL OR latitude BETWEEN -90 AND 90",
  )
  op.create_check_constraint(
    "ck_addresses_longitude_range",
    "addresses",
    "longitude IS NULL OR longitude BETWEEN -180 AND 180",
  )

  op.create_check_constraint(
    "ck_password_resets_otp_hash_not_blank",
    "password_resets",
    "btrim(otp_hash) <> ''",
  )
  op.create_check_constraint(
    "ck_password_resets_expiry_after_request",
    "password_resets",
    "expires_at > requested_at",
  )
  op.create_check_constraint(
    "ck_refresh_sessions_token_hash_length",
    "refresh_sessions",
    "length(token_hash) = 64",
  )
  op.create_check_constraint(
    "ck_refresh_sessions_expiry_after_creation",
    "refresh_sessions",
    "expires_at > created_at",
  )
  op.create_check_constraint(
    "ck_refresh_sessions_revocation_state",
    "refresh_sessions",
    "(revoked_at IS NULL AND revoke_reason IS NULL) OR "
    "(revoked_at IS NOT NULL AND btrim(revoke_reason) <> '')",
  )

  op.create_check_constraint(
    "ck_user_history_email_not_blank",
    "user_history",
    "email <> ''",
  )
  op.create_check_constraint(
    "ck_user_history_first_name_not_blank",
    "user_history",
    "btrim(first_name) <> ''",
  )
  op.create_check_constraint(
    "ck_user_history_last_name_not_blank",
    "user_history",
    "btrim(last_name) <> ''",
  )
  op.create_check_constraint(
    "ck_user_history_change_reason_not_blank",
    "user_history",
    "btrim(change_reason) <> ''",
  )
  op.create_check_constraint(
    "ck_user_history_deactivation_state",
    "user_history",
    "(is_active IS TRUE AND deactivated_at IS NULL) OR "
    "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
  )
  op.create_check_constraint(
    "ck_user_history_anonymization_state",
    "user_history",
    "(anonymized_at IS NULL AND anonymized_by_user_id IS NULL "
    "AND anonymization_reason IS NULL) OR "
    "(anonymized_at IS NOT NULL AND anonymized_by_user_id IS NOT NULL "
    "AND btrim(anonymization_reason) <> '')",
  )

  op.create_check_constraint(
    "ck_office_history_name_not_blank",
    "office_history",
    "btrim(name) <> ''",
  )
  op.create_check_constraint(
    "ck_office_history_services_max_items",
    "office_history",
    "cardinality(services) <= 50",
  )
  op.create_check_constraint(
    "ck_office_history_change_reason_not_blank",
    "office_history",
    "btrim(change_reason) <> ''",
  )
  op.create_check_constraint(
    "ck_office_history_deactivation_state",
    "office_history",
    "(is_active IS TRUE AND deactivated_at IS NULL) OR "
    "(is_active IS FALSE AND deactivated_at IS NOT NULL)",
  )
  op.create_check_constraint(
    "ck_office_history_opening_hours_object",
    "office_history",
    "jsonb_typeof(opening_hours) = 'object'",
  )


def _add_anonymization_audit_fields() -> None:
  op.create_foreign_key(
    "fk_user_history_anonymized_by_user_id_users",
    "user_history",
    "users",
    ["anonymized_by_user_id"],
    ["id"],
    ondelete="RESTRICT",
  )


def _install_history_guards() -> None:
  op.execute(
    f"""
    CREATE OR REPLACE FUNCTION enforce_user_history_immutability()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      target_role text;
      target_deactivated_at timestamptz;
      retention_period interval;
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'user_history is append-only; deletes are forbidden'
          USING ERRCODE = '55000';
      END IF;

      -- The only normal mutation closes a currently-open temporal version.
      IF OLD.valid_to IS NULL
         AND NEW.valid_to IS NOT NULL
         AND NEW.valid_to >= OLD.valid_from
         AND NEW.id IS NOT DISTINCT FROM OLD.id
         AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
         AND NEW.email IS NOT DISTINCT FROM OLD.email
         AND NEW.first_name IS NOT DISTINCT FROM OLD.first_name
         AND NEW.last_name IS NOT DISTINCT FROM OLD.last_name
         AND NEW.role IS NOT DISTINCT FROM OLD.role
         AND NEW.office_id IS NOT DISTINCT FROM OLD.office_id
         AND NEW.is_active IS NOT DISTINCT FROM OLD.is_active
         AND NEW.deactivated_at IS NOT DISTINCT FROM OLD.deactivated_at
         AND NEW.valid_from IS NOT DISTINCT FROM OLD.valid_from
         AND NEW.changed_by_user_id IS NOT DISTINCT FROM OLD.changed_by_user_id
         AND NEW.change_reason IS NOT DISTINCT FROM OLD.change_reason
         AND NEW.anonymized_at IS NOT DISTINCT FROM OLD.anonymized_at
         AND NEW.anonymized_by_user_id IS NOT DISTINCT FROM OLD.anonymized_by_user_id
         AND NEW.anonymization_reason IS NOT DISTINCT FROM OLD.anonymization_reason
      THEN
        RETURN NEW;
      END IF;

      -- Retention redaction is irreversible, narrowly shaped and audited.
      IF OLD.anonymized_at IS NULL
         AND NEW.email = 'deleted@local.com'
         AND NEW.first_name = 'gelöschter'
         AND NEW.last_name = 'Nutzer'
         AND NEW.anonymized_at IS NOT NULL
         AND NEW.anonymized_by_user_id = '{SYSTEM_USER_ID}'::uuid
         AND btrim(NEW.anonymization_reason) <> ''
         AND NEW.id IS NOT DISTINCT FROM OLD.id
         AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
         AND NEW.role IS NOT DISTINCT FROM OLD.role
         AND NEW.office_id IS NOT DISTINCT FROM OLD.office_id
         AND NEW.is_active IS NOT DISTINCT FROM OLD.is_active
         AND NEW.deactivated_at IS NOT DISTINCT FROM OLD.deactivated_at
         AND NEW.valid_from IS NOT DISTINCT FROM OLD.valid_from
         AND NEW.valid_to IS NOT DISTINCT FROM OLD.valid_to
         AND NEW.changed_by_user_id IS NOT DISTINCT FROM OLD.changed_by_user_id
         AND NEW.change_reason IS NOT DISTINCT FROM OLD.change_reason
      THEN
        SELECT role::text, deactivated_at
          INTO target_role, target_deactivated_at
        FROM users
        WHERE id = OLD.user_id;

        retention_period := CASE
          WHEN target_role = 'CITIZEN' THEN interval '180 days'
          ELSE interval '3650 days'
        END;

        IF target_deactivated_at IS NULL
           OR target_deactivated_at > NEW.anonymized_at - retention_period
        THEN
          RAISE EXCEPTION 'user history retention period has not expired'
            USING ERRCODE = '55000';
        END IF;

        RETURN NEW;
      END IF;

      RAISE EXCEPTION 'user_history is immutable outside version closure and retention redaction'
        USING ERRCODE = '55000';
    END;
    $$;
    """
  )

  op.execute(
    """
    CREATE OR REPLACE FUNCTION enforce_office_history_immutability()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'office_history is append-only; deletes are forbidden'
          USING ERRCODE = '55000';
      END IF;

      IF OLD.valid_to IS NULL
         AND NEW.valid_to IS NOT NULL
         AND NEW.valid_to >= OLD.valid_from
         AND NEW.id IS NOT DISTINCT FROM OLD.id
         AND NEW.office_id IS NOT DISTINCT FROM OLD.office_id
         AND NEW.name IS NOT DISTINCT FROM OLD.name
         AND NEW.description IS NOT DISTINCT FROM OLD.description
         AND NEW.contact_email IS NOT DISTINCT FROM OLD.contact_email
         AND NEW.phone IS NOT DISTINCT FROM OLD.phone
         AND NEW.services IS NOT DISTINCT FROM OLD.services
         AND NEW.opening_hours IS NOT DISTINCT FROM OLD.opening_hours
         AND NEW.address_snapshot IS NOT DISTINCT FROM OLD.address_snapshot
         AND NEW.is_active IS NOT DISTINCT FROM OLD.is_active
         AND NEW.deactivated_at IS NOT DISTINCT FROM OLD.deactivated_at
         AND NEW.valid_from IS NOT DISTINCT FROM OLD.valid_from
         AND NEW.changed_by_user_id IS NOT DISTINCT FROM OLD.changed_by_user_id
         AND NEW.change_reason IS NOT DISTINCT FROM OLD.change_reason
      THEN
        RETURN NEW;
      END IF;

      RAISE EXCEPTION 'office_history is immutable outside temporal version closure'
        USING ERRCODE = '55000';
    END;
    $$;
    """
  )

  op.execute(
    """
    CREATE OR REPLACE FUNCTION prevent_history_truncate()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      RAISE EXCEPTION 'history tables are append-only; truncate is forbidden'
        USING ERRCODE = '55000';
    END;
    $$;
    """
  )

  op.execute(
    """
    CREATE TRIGGER trg_user_history_immutable
    BEFORE UPDATE OR DELETE ON user_history
    FOR EACH ROW EXECUTE FUNCTION enforce_user_history_immutability()
    """
  )
  op.execute(
    """
    CREATE TRIGGER trg_office_history_immutable
    BEFORE UPDATE OR DELETE ON office_history
    FOR EACH ROW EXECUTE FUNCTION enforce_office_history_immutability()
    """
  )
  op.execute(
    """
    CREATE TRIGGER trg_user_history_no_truncate
    BEFORE TRUNCATE ON user_history
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_truncate()
    """
  )
  op.execute(
    """
    CREATE TRIGGER trg_office_history_no_truncate
    BEFORE TRUNCATE ON office_history
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_truncate()
    """
  )


def downgrade() -> None:
  op.execute("DROP TRIGGER IF EXISTS trg_office_history_no_truncate ON office_history")
  op.execute("DROP TRIGGER IF EXISTS trg_user_history_no_truncate ON user_history")
  op.execute("DROP TRIGGER IF EXISTS trg_office_history_immutable ON office_history")
  op.execute("DROP TRIGGER IF EXISTS trg_user_history_immutable ON user_history")
  op.execute("DROP FUNCTION IF EXISTS prevent_history_truncate()")
  op.execute("DROP FUNCTION IF EXISTS enforce_office_history_immutability()")
  op.execute("DROP FUNCTION IF EXISTS enforce_user_history_immutability()")

  op.drop_constraint(
    "fk_user_history_anonymized_by_user_id_users",
    "user_history",
    type_="foreignkey",
  )

  for constraint_name, table_name in (
    ("ck_office_history_opening_hours_object", "office_history"),
    ("ck_office_history_deactivation_state", "office_history"),
    ("ck_office_history_change_reason_not_blank", "office_history"),
    ("ck_office_history_services_max_items", "office_history"),
    ("ck_office_history_name_not_blank", "office_history"),
    ("ck_user_history_anonymization_state", "user_history"),
    ("ck_user_history_deactivation_state", "user_history"),
    ("ck_user_history_change_reason_not_blank", "user_history"),
    ("ck_user_history_last_name_not_blank", "user_history"),
    ("ck_user_history_first_name_not_blank", "user_history"),
    ("ck_user_history_email_not_blank", "user_history"),
    ("ck_refresh_sessions_revocation_state", "refresh_sessions"),
    ("ck_refresh_sessions_expiry_after_creation", "refresh_sessions"),
    ("ck_refresh_sessions_token_hash_length", "refresh_sessions"),
    ("ck_password_resets_expiry_after_request", "password_resets"),
    ("ck_password_resets_otp_hash_not_blank", "password_resets"),
    ("ck_addresses_longitude_range", "addresses"),
    ("ck_addresses_latitude_range", "addresses"),
    ("ck_addresses_coordinates_complete", "addresses"),
    ("ck_offices_deactivation_state", "offices"),
    ("ck_offices_contact_email_canonical", "offices"),
    ("ck_offices_name_trimmed", "offices"),
    ("ck_users_deactivation_state", "users"),
    ("ck_users_auth_version_nonnegative", "users"),
    ("ck_users_hashed_password_not_blank", "users"),
    ("ck_users_email_canonical", "users"),
  ):
    op.drop_constraint(constraint_name, table_name, type_="check")

  op.drop_column("user_history", "anonymization_reason")
  op.drop_column("user_history", "anonymized_by_user_id")
  op.drop_column("user_history", "anonymized_at")

  for table_name, column_name, length, nullable in (
    ("office_history", "change_reason", 500, False),
    ("office_history", "phone", 50, True),
    ("office_history", "contact_email", 320, True),
    ("office_history", "description", 500, True),
    ("office_history", "name", 150, False),
    ("offices", "phone", 50, True),
    ("offices", "contact_email", 320, True),
    ("offices", "description", 500, True),
    ("offices", "name", 150, False),
    ("user_history", "change_reason", 500, False),
    ("user_history", "email", 320, False),
    ("users", "email", 320, False),
  ):
    op.alter_column(
      table_name,
      column_name,
      existing_type=sa.String(length=length),
      type_=sa.String(),
      existing_nullable=nullable,
    )

  op.alter_column(
    "office_history",
    "opening_hours",
    existing_type=postgresql.JSONB(),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "office_history",
    "services",
    existing_type=sa.ARRAY(sa.String()),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "office_history",
    "valid_from",
    existing_type=sa.DateTime(timezone=True),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "user_history",
    "valid_from",
    existing_type=sa.DateTime(timezone=True),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "addresses",
    "updated_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=True,
    server_default=None,
  )
  op.alter_column(
    "addresses",
    "created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=True,
    server_default=None,
  )
  op.alter_column(
    "offices",
    "created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=True,
    server_default=None,
  )
  op.alter_column(
    "users",
    "created_at",
    existing_type=sa.DateTime(timezone=True),
    nullable=True,
    server_default=None,
  )
  op.alter_column(
    "offices",
    "opening_hours",
    existing_type=postgresql.JSONB(),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "offices",
    "services",
    existing_type=sa.ARRAY(sa.String()),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "offices",
    "is_active",
    existing_type=sa.Boolean(),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "users",
    "is_active",
    existing_type=sa.Boolean(),
    existing_nullable=False,
    server_default=None,
  )
  op.alter_column(
    "users",
    "role",
    existing_type=sa.Enum(name="role"),
    existing_nullable=False,
    server_default=None,
  )
