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

  assert [str(interval.start) for interval in hours.monday] == [
    "08:00:00",
    "13:00:00",
  ]
  assert hours.sunday == []


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


def test_patch_rejects_null_for_non_nullable_office_fields() -> None:
  from src.office.schemas import OfficeUpdate

  with pytest.raises(ValidationError):
    OfficeUpdate(name=None, change_reason="Administrative correction")
