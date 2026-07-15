import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address
from src.address.repository import AddressRepository
from src.address.schemas import AddressCreate, AddressUpdate
from src.core.exceptions import DomainValidationException, ResourceNotFoundException


class AddressService:
  """Address helpers used inside another domain's transaction."""

  REQUIRED_FIELDS = {"street", "house_number", "zip_code", "city"}

  @staticmethod
  def create_address_entity(address_data: AddressCreate) -> Address:
    return Address(**address_data.model_dump())

  @staticmethod
  def create_address_from_update(address_data: AddressUpdate) -> Address:
    values = address_data.model_dump(exclude_unset=True)
    missing = AddressService.REQUIRED_FIELDS - values.keys()
    if missing:
      raise DomainValidationException(
        "A new address requires street, house_number, zip_code and city.",
        error_code="INCOMPLETE_ADDRESS",
        details=[{"field": field, "message": "Field is required"} for field in sorted(missing)],
      )
    return Address(**values)

  @staticmethod
  def update_address_entity(address: Address, update_data: AddressUpdate) -> Address:
    for key, value in update_data.model_dump(exclude_unset=True).items():
      setattr(address, key, value)
    return address

  @staticmethod
  async def get_address_by_id(db: AsyncSession, address_id: uuid.UUID) -> Address:
    address = await AddressRepository.get_by_id(db, address_id)
    if not address:
      raise ResourceNotFoundException(
        "Address not found",
        error_code="ADDRESS_NOT_FOUND",
      )
    return address
