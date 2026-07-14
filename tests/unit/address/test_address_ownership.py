from sqlalchemy.exc import InvalidRequestError

import src.user.models  # noqa: F401 - register relationship targets
from src.address.models import Address
from src.address.schemas import AddressCreate
from src.office.models import Office


def test_address_strings_are_normalized() -> None:
  payload = AddressCreate(
    street="  Bahnhofstraße\t ",
    house_number="  42 a ",
    zip_code=" 95028 ",
    city="  Bad   Steben ",
  )

  assert payload.street == "Bahnhofstraße"
  assert payload.house_number == "42 a"
  assert payload.zip_code == "95028"
  assert payload.city == "Bad Steben"


def test_address_cannot_be_shared_between_offices() -> None:
  address = Address(
    street="Rathausplatz",
    house_number="1",
    zip_code="95028",
    city="Hof",
  )
  Office(name="Bauamt", address=address)

  try:
    Office(name="Bürgeramt", address=address)
  except InvalidRequestError:
    pass
  else:
    raise AssertionError("an owned address must not be assignable to two offices")


def test_address_update_rejects_null_required_field() -> None:
  from pydantic import ValidationError

  from src.address.schemas import AddressUpdate

  try:
    AddressUpdate(street=None)
  except ValidationError:
    pass
  else:
    raise AssertionError("required address values cannot be cleared with null")
