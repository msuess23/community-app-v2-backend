"""temporal history and user/office domain invariants

Revision ID: e7c9a2f4b6d8
Revises: d4a6f9c1b2e7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e7c9a2f4b6d8"
down_revision: Union[str, Sequence[str], None] = "d4a6f9c1b2e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_USER_EMAIL = "system@internal.example.com"
ROLE_ENUM = postgresql.ENUM(name="role", create_type=False)


def upgrade() -> None:
  # Canonicalize identity fields before introducing case-insensitive indexes.
  # Earlier cleanup steps used the reserved .invalid TLD for deactivated rows;
  # Pydantic's EmailStr correctly rejects that value during API serialization.
  op.execute(
    "UPDATE users SET email = regexp_replace("
    "email, '@users\\.invalid$', '@users.example.com') "
    "WHERE email LIKE '%@users.invalid'"
  )
  op.execute("UPDATE users SET email = lower(btrim(email))")
  op.execute(
    "UPDATE offices "
    "SET name = btrim(regexp_replace(name, '\\s+', ' ', 'g'))"
  )

  op.execute(
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT lower(email)
        FROM users
        GROUP BY lower(email)
        HAVING count(*) > 1
      ) THEN
        RAISE EXCEPTION
          'Cannot create case-insensitive user email constraint: duplicates exist';
      END IF;

      IF EXISTS (
        SELECT lower(name)
        FROM offices
        WHERE is_active IS TRUE
        GROUP BY lower(name)
        HAVING count(*) > 1
      ) THEN
        RAISE EXCEPTION
          'Cannot create active office name constraint: duplicates exist';
      END IF;
    END
    $$;
    """
  )

  op.execute("UPDATE users SET role = 'CITIZEN' WHERE role IS NULL")
  op.execute("UPDATE users SET is_active = true WHERE is_active IS NULL")
  op.execute("UPDATE offices SET is_active = true WHERE is_active IS NULL")

  # Persist a real technical principal before actor foreign keys are added.
  op.execute(
    sa.text(
      """
      INSERT INTO users (
        id, email, hashed_password, first_name, last_name, role, office_id,
        is_active, auth_version, created_at, deactivated_at
      )
      VALUES (
        CAST(:system_user_id AS uuid), :system_email,
        '!system-principal-no-login!', 'System', 'Principal', 'ADMIN', NULL,
        false, 0, now(), now()
      )
      ON CONFLICT (id) DO NOTHING
      """
    ).bindparams(
      system_user_id=SYSTEM_USER_ID,
      system_email=SYSTEM_USER_EMAIL,
    )
  )

  # Normalize states that can be repaired unambiguously, then reject states for
  # which a migration cannot safely invent a business assignment.
  op.execute(
    "UPDATE users SET office_id = NULL "
    "WHERE role IN ('CITIZEN', 'ADMIN')"
  )
  op.execute(
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM users
        WHERE role IN ('DISPATCHER', 'OFFICER', 'MANAGER')
          AND office_id IS NULL
      ) THEN
        RAISE EXCEPTION
          'Staff users without an office must be corrected before migration';
      END IF;

      IF EXISTS (
        SELECT 1
        FROM users u
        JOIN offices o ON o.id = u.office_id
        WHERE u.is_active IS TRUE
          AND u.role IN ('DISPATCHER', 'OFFICER', 'MANAGER')
          AND o.is_active IS NOT TRUE
      ) THEN
        RAISE EXCEPTION
          'Active staff assigned to inactive offices must be corrected before migration';
      END IF;
    END
    $$;
    """
  )

  op.alter_column("users", "role", existing_type=ROLE_ENUM, nullable=False)
  op.alter_column("users", "is_active", existing_type=sa.Boolean(), nullable=False)
  op.alter_column("offices", "is_active", existing_type=sa.Boolean(), nullable=False)

  op.drop_index(op.f("ix_users_email"), table_name="users")
  op.create_index(
    "uq_users_email_ci",
    "users",
    [sa.text("lower(email)")],
    unique=True,
  )
  op.create_index(
    "uq_offices_active_name_ci",
    "offices",
    [sa.text("lower(name)")],
    unique=True,
    postgresql_where=sa.text("is_active IS TRUE"),
  )
  op.create_check_constraint(
    "ck_users_role_office_assignment",
    "users",
    "((role IN ('CITIZEN', 'ADMIN') AND office_id IS NULL) "
    "OR (role IN ('DISPATCHER', 'OFFICER', 'MANAGER') "
    "AND office_id IS NOT NULL))",
  )

  _upgrade_user_history()
  _upgrade_office_history()


def _upgrade_user_history() -> None:
  op.alter_column(
    "user_history",
    "changed_at",
    new_column_name="valid_from",
    existing_type=sa.DateTime(timezone=True),
  )
  op.add_column(
    "user_history",
    sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
  )
  op.add_column(
    "user_history",
    sa.Column("office_id", sa.UUID(), nullable=True),
  )
  op.add_column(
    "user_history",
    sa.Column("is_active", sa.Boolean(), nullable=True),
  )
  op.add_column(
    "user_history",
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
  )

  op.execute("UPDATE user_history SET valid_from = now() WHERE valid_from IS NULL")
  op.execute(
    """
    WITH ranked AS (
      SELECT id, user_id,
             row_number() OVER (
               PARTITION BY user_id ORDER BY valid_from DESC, id DESC
             ) AS position
      FROM user_history
    )
    UPDATE user_history AS h
    SET email = CASE WHEN r.position = 1 THEN u.email ELSE h.email END,
        first_name = CASE WHEN r.position = 1 THEN u.first_name ELSE h.first_name END,
        last_name = CASE WHEN r.position = 1 THEN u.last_name ELSE h.last_name END,
        role = CASE WHEN r.position = 1 THEN u.role ELSE h.role END,
        office_id = u.office_id,
        is_active = CASE WHEN r.position = 1 THEN u.is_active ELSE true END,
        deactivated_at = CASE
          WHEN r.position = 1 THEN u.deactivated_at ELSE NULL
        END
    FROM ranked r
    JOIN users u ON u.id = r.user_id
    WHERE h.id = r.id
    """
  )

  # Repair legacy dummy actor UUIDs to the persisted system principal.
  op.execute(
    sa.text(
      """
      UPDATE user_history AS h
      SET changed_by_user_id = CAST(:system_user_id AS uuid)
      WHERE changed_by_user_id IS NULL
         OR NOT EXISTS (
           SELECT 1 FROM users actor WHERE actor.id = h.changed_by_user_id
         )
      """
    ).bindparams(system_user_id=SYSTEM_USER_ID)
  )

  # Defensive backfill for users that existed without any audit row.
  op.execute(
    sa.text(
      """
      INSERT INTO user_history (
        id, user_id, email, first_name, last_name, role, office_id,
        is_active, deactivated_at, valid_from, valid_to,
        changed_by_user_id, change_reason
      )
      SELECT md5('user-history-' || u.id::text)::uuid, u.id, u.email, u.first_name, u.last_name,
             u.role, u.office_id, u.is_active, u.deactivated_at,
             u.created_at, NULL, CAST(:system_user_id AS uuid),
             'Legacy snapshot backfilled by migration'
      FROM users u
      WHERE NOT EXISTS (
        SELECT 1 FROM user_history h WHERE h.user_id = u.id
      )
      """
    ).bindparams(system_user_id=SYSTEM_USER_ID)
  )

  # Convert a sequence of snapshot timestamps into half-open validity periods.
  op.execute(
    """
    WITH periods AS (
      SELECT id,
             lead(valid_from) OVER (
               PARTITION BY user_id ORDER BY valid_from, id
             ) AS next_valid_from
      FROM user_history
    )
    UPDATE user_history AS h
    SET valid_to = p.next_valid_from
    FROM periods p
    WHERE h.id = p.id
    """
  )

  op.alter_column("user_history", "user_id", existing_type=sa.UUID(), nullable=False)
  op.alter_column("user_history", "email", existing_type=sa.String(), nullable=False)
  op.alter_column("user_history", "first_name", existing_type=sa.String(), nullable=False)
  op.alter_column("user_history", "last_name", existing_type=sa.String(), nullable=False)
  op.alter_column("user_history", "role", existing_type=ROLE_ENUM, nullable=False)
  op.alter_column(
    "user_history",
    "valid_from",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
  )
  op.alter_column("user_history", "is_active", existing_type=sa.Boolean(), nullable=False)
  op.alter_column(
    "user_history",
    "changed_by_user_id",
    existing_type=sa.UUID(),
    nullable=False,
  )

  op.create_foreign_key(
    "fk_user_history_office_id_offices",
    "user_history",
    "offices",
    ["office_id"],
    ["id"],
    ondelete="RESTRICT",
  )
  op.create_foreign_key(
    "fk_user_history_changed_by_user_id_users",
    "user_history",
    "users",
    ["changed_by_user_id"],
    ["id"],
    ondelete="RESTRICT",
  )
  op.create_check_constraint(
    "ck_user_history_valid_period",
    "user_history",
    "valid_to IS NULL OR valid_to >= valid_from",
  )
  op.create_index(
    "uq_user_history_current_version",
    "user_history",
    ["user_id"],
    unique=True,
    postgresql_where=sa.text("valid_to IS NULL"),
  )


def _upgrade_office_history() -> None:
  op.alter_column(
    "office_history",
    "changed_at",
    new_column_name="valid_from",
    existing_type=sa.DateTime(timezone=True),
  )
  op.add_column(
    "office_history",
    sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
  )
  op.add_column(
    "office_history",
    sa.Column("is_active", sa.Boolean(), nullable=True),
  )
  op.add_column(
    "office_history",
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
  )
  op.alter_column(
    "office_history",
    "address_snapshot",
    existing_type=sa.String(),
    type_=postgresql.JSONB(astext_type=sa.Text()),
    existing_nullable=True,
    postgresql_using=(
      "CASE WHEN address_snapshot IS NULL THEN NULL "
      "ELSE jsonb_build_object('formatted', address_snapshot) END"
    ),
  )

  op.execute("UPDATE office_history SET valid_from = now() WHERE valid_from IS NULL")
  op.execute("UPDATE office_history SET services = '{}' WHERE services IS NULL")
  op.execute("UPDATE office_history SET opening_hours = '{}'::jsonb WHERE opening_hours IS NULL")
  op.execute(
    """
    WITH ranked AS (
      SELECT id, office_id,
             row_number() OVER (
               PARTITION BY office_id ORDER BY valid_from DESC, id DESC
             ) AS position
      FROM office_history
    )
    UPDATE office_history AS h
    SET name = CASE WHEN r.position = 1 THEN o.name ELSE h.name END,
        description = CASE WHEN r.position = 1 THEN o.description ELSE h.description END,
        contact_email = CASE WHEN r.position = 1 THEN o.contact_email ELSE h.contact_email END,
        phone = CASE WHEN r.position = 1 THEN o.phone ELSE h.phone END,
        services = CASE WHEN r.position = 1 THEN COALESCE(o.services, '{}') ELSE h.services END,
        opening_hours = CASE
          WHEN r.position = 1 THEN COALESCE(o.opening_hours, '{}'::jsonb)
          ELSE h.opening_hours
        END,
        address_snapshot = CASE
          WHEN r.position = 1 AND a.id IS NOT NULL THEN jsonb_build_object(
            'id', a.id::text,
            'street', a.street,
            'house_number', a.house_number,
            'zip_code', a.zip_code,
            'city', a.city,
            'latitude', a.latitude,
            'longitude', a.longitude
          )
          WHEN r.position = 1 THEN NULL
          ELSE h.address_snapshot
        END,
        is_active = CASE WHEN r.position = 1 THEN o.is_active ELSE true END,
        deactivated_at = CASE
          WHEN r.position = 1 THEN o.deactivated_at ELSE NULL
        END
    FROM ranked r
    JOIN offices o ON o.id = r.office_id
    LEFT JOIN addresses a ON a.id = o.address_id
    WHERE h.id = r.id
    """
  )
  op.execute(
    sa.text(
      """
      UPDATE office_history AS h
      SET changed_by_user_id = CAST(:system_user_id AS uuid)
      WHERE changed_by_user_id IS NULL
         OR NOT EXISTS (
           SELECT 1 FROM users actor WHERE actor.id = h.changed_by_user_id
         )
      """
    ).bindparams(system_user_id=SYSTEM_USER_ID)
  )

  op.execute(
    sa.text(
      """
      INSERT INTO office_history (
        id, office_id, name, description, contact_email, phone, services,
        opening_hours, address_snapshot, is_active, deactivated_at,
        valid_from, valid_to, changed_by_user_id, change_reason
      )
      SELECT md5('office-history-' || o.id::text)::uuid, o.id, o.name, o.description, o.contact_email,
             o.phone, COALESCE(o.services, '{}'),
             COALESCE(o.opening_hours, '{}'::jsonb),
             CASE WHEN a.id IS NULL THEN NULL ELSE jsonb_build_object(
               'id', a.id::text,
               'street', a.street,
               'house_number', a.house_number,
               'zip_code', a.zip_code,
               'city', a.city,
               'latitude', a.latitude,
               'longitude', a.longitude
             ) END,
             o.is_active, o.deactivated_at, o.created_at, NULL,
             CAST(:system_user_id AS uuid),
             'Legacy snapshot backfilled by migration'
      FROM offices o
      LEFT JOIN addresses a ON a.id = o.address_id
      WHERE NOT EXISTS (
        SELECT 1 FROM office_history h WHERE h.office_id = o.id
      )
      """
    ).bindparams(system_user_id=SYSTEM_USER_ID)
  )

  op.execute(
    """
    WITH periods AS (
      SELECT id,
             lead(valid_from) OVER (
               PARTITION BY office_id ORDER BY valid_from, id
             ) AS next_valid_from
      FROM office_history
    )
    UPDATE office_history AS h
    SET valid_to = p.next_valid_from
    FROM periods p
    WHERE h.id = p.id
    """
  )

  op.alter_column("office_history", "office_id", existing_type=sa.UUID(), nullable=False)
  op.alter_column("office_history", "name", existing_type=sa.String(), nullable=False)
  op.alter_column(
    "office_history",
    "services",
    existing_type=postgresql.ARRAY(sa.String()),
    nullable=False,
  )
  op.alter_column(
    "office_history",
    "opening_hours",
    existing_type=postgresql.JSONB(astext_type=sa.Text()),
    nullable=False,
  )
  op.alter_column(
    "office_history",
    "valid_from",
    existing_type=sa.DateTime(timezone=True),
    nullable=False,
  )
  op.alter_column("office_history", "is_active", existing_type=sa.Boolean(), nullable=False)
  op.alter_column(
    "office_history",
    "changed_by_user_id",
    existing_type=sa.UUID(),
    nullable=False,
  )

  op.create_foreign_key(
    "fk_office_history_changed_by_user_id_users",
    "office_history",
    "users",
    ["changed_by_user_id"],
    ["id"],
    ondelete="RESTRICT",
  )
  op.create_check_constraint(
    "ck_office_history_valid_period",
    "office_history",
    "valid_to IS NULL OR valid_to >= valid_from",
  )
  op.create_index(
    "uq_office_history_current_version",
    "office_history",
    ["office_id"],
    unique=True,
    postgresql_where=sa.text("valid_to IS NULL"),
  )


def downgrade() -> None:
  op.drop_index("uq_office_history_current_version", table_name="office_history")
  op.drop_constraint(
    "ck_office_history_valid_period",
    "office_history",
    type_="check",
  )
  op.drop_constraint(
    "fk_office_history_changed_by_user_id_users",
    "office_history",
    type_="foreignkey",
  )
  op.alter_column(
    "office_history",
    "address_snapshot",
    existing_type=postgresql.JSONB(astext_type=sa.Text()),
    type_=sa.String(),
    existing_nullable=True,
    postgresql_using=(
      "COALESCE(address_snapshot->>'formatted', "
      "concat_ws(', ', concat_ws(' ', address_snapshot->>'street', "
      "address_snapshot->>'house_number'), concat_ws(' ', "
      "address_snapshot->>'zip_code', address_snapshot->>'city')))"
    ),
  )
  op.drop_column("office_history", "deactivated_at")
  op.drop_column("office_history", "is_active")
  op.drop_column("office_history", "valid_to")
  op.alter_column(
    "office_history",
    "valid_from",
    new_column_name="changed_at",
    existing_type=sa.DateTime(timezone=True),
  )

  op.drop_index("uq_user_history_current_version", table_name="user_history")
  op.drop_constraint(
    "ck_user_history_valid_period",
    "user_history",
    type_="check",
  )
  op.drop_constraint(
    "fk_user_history_changed_by_user_id_users",
    "user_history",
    type_="foreignkey",
  )
  op.drop_constraint(
    "fk_user_history_office_id_offices",
    "user_history",
    type_="foreignkey",
  )
  op.execute(
    sa.text(
      "DELETE FROM user_history "
      "WHERE user_id = CAST(:system_user_id AS uuid)"
    ).bindparams(system_user_id=SYSTEM_USER_ID)
  )
  op.drop_column("user_history", "deactivated_at")
  op.drop_column("user_history", "is_active")
  op.drop_column("user_history", "office_id")
  op.drop_column("user_history", "valid_to")
  op.alter_column(
    "user_history",
    "valid_from",
    new_column_name="changed_at",
    existing_type=sa.DateTime(timezone=True),
  )

  op.alter_column("user_history", "user_id", existing_type=sa.UUID(), nullable=True)
  op.alter_column("user_history", "email", existing_type=sa.String(), nullable=True)
  op.alter_column("user_history", "first_name", existing_type=sa.String(), nullable=True)
  op.alter_column("user_history", "last_name", existing_type=sa.String(), nullable=True)
  op.alter_column("user_history", "role", existing_type=ROLE_ENUM, nullable=True)
  op.alter_column(
    "user_history",
    "changed_by_user_id",
    existing_type=sa.UUID(),
    nullable=True,
  )
  op.alter_column("office_history", "office_id", existing_type=sa.UUID(), nullable=True)
  op.alter_column("office_history", "name", existing_type=sa.String(), nullable=True)
  op.alter_column(
    "office_history",
    "services",
    existing_type=postgresql.ARRAY(sa.String()),
    nullable=True,
  )
  op.alter_column(
    "office_history",
    "opening_hours",
    existing_type=postgresql.JSONB(astext_type=sa.Text()),
    nullable=True,
  )
  op.alter_column(
    "office_history",
    "changed_by_user_id",
    existing_type=sa.UUID(),
    nullable=True,
  )
  op.alter_column("users", "role", existing_type=ROLE_ENUM, nullable=True)
  op.alter_column("users", "is_active", existing_type=sa.Boolean(), nullable=True)
  op.alter_column("offices", "is_active", existing_type=sa.Boolean(), nullable=True)

  op.drop_constraint("ck_users_role_office_assignment", "users", type_="check")
  op.drop_index("uq_offices_active_name_ci", table_name="offices")
  op.drop_index("uq_users_email_ci", table_name="users")
  op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

  op.execute(
    sa.text(
      "DELETE FROM users WHERE id = CAST(:system_user_id AS uuid) "
      "AND email = :system_email"
    ).bindparams(
      system_user_id=SYSTEM_USER_ID,
      system_email=SYSTEM_USER_EMAIL,
    )
  )
