import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DomainException
from src.address.models import Address
from src.address.schemas import AddressCreate, AddressUpdate
from src.address.repository import AddressRepository

class AddressService:
  """
  Handles business logic for addresses.
  Designed to be called by other domain services within an existing transaction.
  """

  @staticmethod
  def create_address_entity(address_data: AddressCreate) -> Address:
    """
    Instantiates a new Address entity from creation data.
    Does NOT commit to the database. The calling service must handle the transaction.
    """
    return Address(
      street=address_data.street,
      house_number=address_data.house_number,
      zip_code=address_data.zip_code,
      city=address_data.city,
      latitude=address_data.latitude,
      longitude=address_data.longitude
    )

  @staticmethod
  def update_address_entity(address: Address, update_data: AddressUpdate) -> Address:
    """
    Applies updates to an existing Address entity.
    Does NOT commit to the database.
    """
    update_dict = update_data.model_dump(exclude_unset=True)
    
    for key, value in update_dict.items():
      setattr(address, key, value)
      
    return address
    
  @staticmethod
  async def get_address_by_id(db: AsyncSession, address_id: uuid.UUID) -> Address:
    """
    Retrieves an address by ID or raises a DomainException if not found.
    """
    address = await AddressRepository.get_by_id(db, address_id)
    if not address:
      raise DomainException("Address not found", status_code=404)
    return address