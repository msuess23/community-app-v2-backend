"""office API, address ownership, and validation hardening

Revision ID: f8d0b3c5a7e9
Revises: e7c9a2f4b6d8
"""

from __future__ import annotations

import json
import re
from datetime import time
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8d0b3c5a7e9"
down_revision: Union[str, Sequence[str], None] = "e7c9a2f4b6d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WEEKDAYS = (
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
)
_INTERVAL_RE = re.compile(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$")
_CLOSED_VALUES = {"", "closed", "geschlossen"}


def _parse_clock(value: str) -> str:
  try:
    hour_text, minute_text = value.split(":", maxsplit=1)
    parsed = time(hour=int(hour_text), minute=int(minute_text))
  except (TypeError, ValueError) as exc:
    raise RuntimeError(f"Invalid clock value: {value}") from exc
  return parsed.strftime("%H:%M:%S")


def _normalize_day(value: Any, *, row_label: str, weekday: str) -> dict[str, Any]:
  if value is None:
    return {"closed": True, "intervals": []}

  if isinstance(value, dict):
    intervals = value.get("intervals", [])
    closed = bool(value.get("closed", not intervals))
    normalized_intervals = []
    for interval in intervals:
      if not isinstance(interval, dict):
        raise RuntimeError(
          f"Invalid opening-hours interval for {row_label} on {weekday}"
        )
      start = _parse_clock(str(interval.get("start", "")))
      end = _parse_clock(str(interval.get("end", "")))
      if start >= end:
        raise RuntimeError(
          f"Opening-hours start must be before end for {row_label} on {weekday}"
        )
      normalized_intervals.append({"start": start, "end": end})
    if closed and normalized_intervals:
      raise RuntimeError(
        f"Closed day contains intervals for {row_label} on {weekday}"
      )
    if not closed and not normalized_intervals:
      raise RuntimeError(
        f"Open day contains no interval for {row_label} on {weekday}"
      )
    normalized_intervals.sort(key=lambda interval: interval["start"])
    for previous, current in zip(normalized_intervals, normalized_intervals[1:]):
      if previous["end"] > current["start"]:
        raise RuntimeError(
          f"Opening-hours intervals overlap for {row_label} on {weekday}"
        )
    return {"closed": closed, "intervals": normalized_intervals}

  if not isinstance(value, str):
    raise RuntimeError(f"Invalid opening-hours value for {row_label} on {weekday}")

  stripped = value.strip()
  if stripped.casefold() in _CLOSED_VALUES:
    return {"closed": True, "intervals": []}

  intervals = []
  for raw_interval in stripped.split(","):
    match = _INTERVAL_RE.fullmatch(raw_interval.strip())
    if match is None:
      raise RuntimeError(
        f"Cannot migrate opening hours '{value}' for {row_label} on {weekday}"
      )
    start = _parse_clock(match.group(1))
    end = _parse_clock(match.group(2))
    if start >= end:
      raise RuntimeError(
        f"Opening-hours start must be before end for {row_label} on {weekday}"
      )
    intervals.append({"start": start, "end": end})
  intervals.sort(key=lambda interval: interval["start"])
  for previous, current in zip(intervals, intervals[1:]):
    if previous["end"] > current["start"]:
      raise RuntimeError(
        f"Opening-hours intervals overlap for {row_label} on {weekday}"
      )
  return {"closed": False, "intervals": intervals}


def _normalize_opening_hours(value: Any, *, row_label: str) -> dict[str, Any]:
  if value in (None, {}):
    return {}
  if not isinstance(value, dict):
    raise RuntimeError(f"Opening hours for {row_label} must be a JSON object")

  unknown = set(value) - set(_WEEKDAYS)
  if unknown:
    raise RuntimeError(
      f"Unknown opening-hours keys for {row_label}: {', '.join(sorted(unknown))}"
    )

  return {
    weekday: _normalize_day(day_value, row_label=row_label, weekday=weekday)
    for weekday, day_value in value.items()
  }


def _migrate_opening_hours(table_name: str) -> None:
  connection = op.get_bind()
  rows = connection.execute(
    sa.text(f"SELECT id, opening_hours FROM {table_name}")
  ).mappings()
  update_statement = sa.text(
    f"UPDATE {table_name} "
    "SET opening_hours = CAST(:opening_hours AS jsonb) WHERE id = :id"
  )
  for row in rows:
    normalized = _normalize_opening_hours(
      row["opening_hours"],
      row_label=f"{table_name}:{row['id']}",
    )
    connection.execute(
      update_statement,
      {"id": row["id"], "opening_hours": json.dumps(normalized)},
    )


def upgrade() -> None:
  op.execute(
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT address_id
        FROM offices
        WHERE address_id IS NOT NULL
        GROUP BY address_id
        HAVING count(*) > 1
      ) THEN
        RAISE EXCEPTION
          'An address is referenced by multiple offices; split shared addresses before migration';
      END IF;
    END
    $$;
    """
  )

  op.execute(
    "UPDATE users SET first_name = btrim(first_name), last_name = btrim(last_name)"
  )
  op.execute(
    "UPDATE user_history "
    "SET first_name = btrim(first_name), last_name = btrim(last_name)"
  )
  op.execute(
    "UPDATE addresses SET street = btrim(street), "
    "house_number = btrim(house_number), zip_code = btrim(zip_code), city = btrim(city)"
  )
  op.execute(
    "UPDATE offices SET description = NULLIF(btrim(description), ''), "
    "phone = NULLIF(btrim(phone), ''), "
    "contact_email = CASE WHEN contact_email IS NULL THEN NULL "
    "ELSE lower(btrim(contact_email)) END"
  )

  op.execute(
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM users
        WHERE first_name = '' OR last_name = ''
           OR length(first_name) > 100 OR length(last_name) > 100
      ) THEN
        RAISE EXCEPTION 'User names are blank or exceed 100 characters';
      END IF;

      IF EXISTS (
        SELECT 1 FROM user_history
        WHERE first_name = '' OR last_name = ''
           OR length(first_name) > 100 OR length(last_name) > 100
      ) THEN
        RAISE EXCEPTION 'Historical user names are blank or exceed 100 characters';
      END IF;

      IF EXISTS (
        SELECT 1 FROM addresses
        WHERE street = '' OR house_number = '' OR zip_code = '' OR city = ''
           OR length(street) > 150 OR length(house_number) > 20
           OR length(zip_code) > 20 OR length(city) > 100
      ) THEN
        RAISE EXCEPTION 'Address values are blank or exceed the new field limits';
      END IF;
    END
    $$;
    """
  )

  _migrate_opening_hours("offices")
  _migrate_opening_hours("office_history")

  op.alter_column(
    "users",
    "first_name",
    existing_type=sa.String(),
    type_=sa.String(length=100),
    existing_nullable=False,
  )
  op.alter_column(
    "users",
    "last_name",
    existing_type=sa.String(),
    type_=sa.String(length=100),
    existing_nullable=False,
  )
  op.alter_column(
    "user_history",
    "first_name",
    existing_type=sa.String(),
    type_=sa.String(length=100),
    existing_nullable=False,
  )
  op.alter_column(
    "user_history",
    "last_name",
    existing_type=sa.String(),
    type_=sa.String(length=100),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "street",
    existing_type=sa.String(),
    type_=sa.String(length=150),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "house_number",
    existing_type=sa.String(),
    type_=sa.String(length=20),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "zip_code",
    existing_type=sa.String(),
    type_=sa.String(length=20),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "city",
    existing_type=sa.String(),
    type_=sa.String(length=100),
    existing_nullable=False,
  )

  op.create_unique_constraint(
    "uq_offices_address_id",
    "offices",
    ["address_id"],
  )
  op.create_check_constraint(
    "ck_addresses_street_not_blank",
    "addresses",
    "btrim(street) <> ''",
  )
  op.create_check_constraint(
    "ck_addresses_house_number_not_blank",
    "addresses",
    "btrim(house_number) <> ''",
  )
  op.create_check_constraint(
    "ck_addresses_zip_code_not_blank",
    "addresses",
    "btrim(zip_code) <> ''",
  )
  op.create_check_constraint(
    "ck_addresses_city_not_blank",
    "addresses",
    "btrim(city) <> ''",
  )
  op.create_check_constraint(
    "ck_users_first_name_not_blank",
    "users",
    "btrim(first_name) <> ''",
  )
  op.create_check_constraint(
    "ck_users_last_name_not_blank",
    "users",
    "btrim(last_name) <> ''",
  )
  op.create_check_constraint(
    "ck_offices_name_not_blank",
    "offices",
    "btrim(name) <> ''",
  )
  op.create_check_constraint(
    "ck_offices_services_max_items",
    "offices",
    "cardinality(services) <= 50",
  )
  op.create_check_constraint(
    "ck_offices_opening_hours_object",
    "offices",
    "jsonb_typeof(opening_hours) = 'object'",
  )

  op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
  op.execute(
    "CREATE INDEX ix_users_email_trgm ON users "
    "USING gin (lower(email) gin_trgm_ops)"
  )
  op.execute(
    "CREATE INDEX ix_users_first_name_trgm ON users "
    "USING gin (lower(first_name) gin_trgm_ops)"
  )
  op.execute(
    "CREATE INDEX ix_users_last_name_trgm ON users "
    "USING gin (lower(last_name) gin_trgm_ops)"
  )
  op.execute(
    "CREATE INDEX ix_offices_name_trgm ON offices "
    "USING gin (lower(name) gin_trgm_ops)"
  )
  op.execute(
    "CREATE INDEX ix_offices_description_trgm ON offices "
    "USING gin (lower(description) gin_trgm_ops)"
  )


def downgrade() -> None:
  op.execute("DROP INDEX IF EXISTS ix_offices_description_trgm")
  op.execute("DROP INDEX IF EXISTS ix_offices_name_trgm")
  op.execute("DROP INDEX IF EXISTS ix_users_last_name_trgm")
  op.execute("DROP INDEX IF EXISTS ix_users_first_name_trgm")
  op.execute("DROP INDEX IF EXISTS ix_users_email_trgm")

  op.drop_constraint("ck_offices_opening_hours_object", "offices", type_="check")
  op.drop_constraint("ck_offices_services_max_items", "offices", type_="check")
  op.drop_constraint("ck_offices_name_not_blank", "offices", type_="check")
  op.drop_constraint("ck_users_last_name_not_blank", "users", type_="check")
  op.drop_constraint("ck_users_first_name_not_blank", "users", type_="check")
  op.drop_constraint("ck_addresses_city_not_blank", "addresses", type_="check")
  op.drop_constraint("ck_addresses_zip_code_not_blank", "addresses", type_="check")
  op.drop_constraint(
    "ck_addresses_house_number_not_blank",
    "addresses",
    type_="check",
  )
  op.drop_constraint("ck_addresses_street_not_blank", "addresses", type_="check")
  op.drop_constraint("uq_offices_address_id", "offices", type_="unique")

  op.alter_column(
    "addresses",
    "city",
    existing_type=sa.String(length=100),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "zip_code",
    existing_type=sa.String(length=20),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "house_number",
    existing_type=sa.String(length=20),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "addresses",
    "street",
    existing_type=sa.String(length=150),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "user_history",
    "last_name",
    existing_type=sa.String(length=100),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "user_history",
    "first_name",
    existing_type=sa.String(length=100),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "users",
    "last_name",
    existing_type=sa.String(length=100),
    type_=sa.String(),
    existing_nullable=False,
  )
  op.alter_column(
    "users",
    "first_name",
    existing_type=sa.String(length=100),
    type_=sa.String(),
    existing_nullable=False,
  )
