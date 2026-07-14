import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address
from src.address.repository import AddressRepository
from src.address.schemas import AddressCreate, AddressUpdate
from src.core.exceptions import ResourceNotFoundException


class AddressService:
  """Business helpers for addresses owned by an office."""

  @staticmethod
  def create_address_entity(address_data: AddressCreate) -> Address:
    return Address(**address_data.model_dump())

  @staticmethod
  def update_address_entity(address: Address, update_data: AddressUpdate) -> Address:
    for key, value in update_data.model_dump(exclude_unset=True).items():
      setattr(address, key, value)
    return address

  @staticmethod
  async def get_address_by_id(db: AsyncSession, address_id: uuid.UUID) -> Address:
    address = await AddressRepository.get_by_id(db, address_id)
    if address is None:
      raise ResourceNotFoundException(
        "Address not found",
        error_code="ADDRESS_NOT_FOUND",
      )
    return address
