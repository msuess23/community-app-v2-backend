from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.office.schemas import (
  OfficeCreate,
  OfficeHistoryResponse,
  OfficeUpdate,
  OpeningHours,
)


def test_office_strings_and_services_are_normalized():
  office = OfficeCreate(
    name="  Bürger   Service  ",
    description="  Hilft   Bürgern  ",
    services=[" Ausweis ", "ausweis", " Reisepass "],
  )

  assert office.name == "Bürger Service"
  assert office.description == "Hilft Bürgern"
  assert office.services == ["Ausweis", "Reisepass"]


def test_opening_hours_are_normalized():
  hours = OpeningHours(monday="13:00-16:00, 08:00-12:00")
  assert hours.monday == "08:00-12:00, 13:00-16:00"


@pytest.mark.parametrize(
  "value",
  ["08:00", "12:00-08:00", "08:00-12:00, 11:00-13:00", "25:00-26:00"],
)
def test_invalid_opening_hours_are_rejected(value: str):
  with pytest.raises(ValidationError):
    OpeningHours(monday=value)


def test_office_requests_reject_unknown_fields_and_null_required_updates():
  with pytest.raises(ValidationError):
    OfficeCreate(name="Test Office", unexpected=True)

  with pytest.raises(ValidationError):
    OfficeUpdate(name=None, change_reason="Invalid name")

  with pytest.raises(ValidationError):
    OfficeUpdate(services=None, change_reason="Invalid services")

  update = OfficeUpdate(
    description=None,
    address=None,
    change_reason="Clear optional fields",
  )
  assert update.description is None
  assert update.address is None


def test_office_history_uses_typed_opening_hours():
  history = OfficeHistoryResponse(
    id=uuid4(),
    office_id=uuid4(),
    name="Testamt",
    opening_hours={"monday": "08:00-12:00"},
    is_active=True,
    changed_by_user_id=uuid4(),
    change_reason="Opening hours changed",
    changed_at=datetime.now(timezone.utc),
  )

  assert isinstance(history.opening_hours, OpeningHours)
  assert history.opening_hours.monday == "08:00-12:00"
