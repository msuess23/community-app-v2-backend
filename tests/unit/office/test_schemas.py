import pytest
from pydantic import ValidationError

from src.office.schemas import OfficeCreate, OpeningHours


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
