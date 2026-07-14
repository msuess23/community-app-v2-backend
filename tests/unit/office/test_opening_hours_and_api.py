import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.main import app
from src.office.schemas import OfficeCreate, OpeningHours


def test_opening_hours_are_structured_and_sorted() -> None:
  hours = OpeningHours(
    monday={
      "intervals": [
        {"start": "13:00", "end": "16:00"},
        {"start": "08:00", "end": "12:00"},
      ]
    }
  )

  assert hours.monday.closed is False
  assert [str(interval.start) for interval in hours.monday.intervals] == [
    "08:00:00",
    "13:00:00",
  ]
  assert hours.sunday.closed is True


def test_overlapping_opening_hours_are_rejected() -> None:
  with pytest.raises(ValidationError):
    OpeningHours(
      monday={
        "intervals": [
          {"start": "08:00", "end": "12:00"},
          {"start": "11:00", "end": "13:00"},
        ]
      }
    )


def test_office_services_are_normalized_and_deduplicated() -> None:
  payload = OfficeCreate(
    name=" Bürgeramt Nord ",
    services=[" Reisepass ", "reisepass", "  Personalausweis  "],
  )

  assert payload.services == ["Reisepass", "Personalausweis"]


def test_public_office_routes_do_not_expose_lifecycle_filter() -> None:
  schema = app.openapi()
  public_parameters = {
    parameter["name"]
    for parameter in schema["paths"]["/api/v1/offices"]["get"]["parameters"]
  }
  admin_parameters = {
    parameter["name"]
    for parameter in schema["paths"]["/api/v1/offices/admin"]["get"]["parameters"]
  }

  assert "status" not in public_parameters
  assert "status" in admin_parameters
  assert "/api/v1/offices/admin/{office_id}" in schema["paths"]


def test_legacy_opening_hours_migration_parser() -> None:
  migration_path = (
    Path(__file__).parents[3]
    / "alembic/versions/f8d0b3c5a7e9_office_api_and_validation_hardening.py"
  )
  spec = importlib.util.spec_from_file_location("step7_migration", migration_path)
  assert spec is not None and spec.loader is not None
  migration = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(migration)

  normalized = migration._normalize_opening_hours(
    {"monday": "08:00-12:00, 13:00-16:00", "sunday": "geschlossen"},
    row_label="test",
  )

  assert normalized["monday"] == {
    "closed": False,
    "intervals": [
      {"start": "08:00:00", "end": "12:00:00"},
      {"start": "13:00:00", "end": "16:00:00"},
    ],
  }
  assert normalized["sunday"] == {"closed": True, "intervals": []}


def test_patch_rejects_null_for_non_nullable_office_fields() -> None:
  from src.office.schemas import OfficeUpdate

  with pytest.raises(ValidationError):
    OfficeUpdate(name=None, change_reason="Administrative correction")
