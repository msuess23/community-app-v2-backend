import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.address.models import Address

class AddressRepository:
  """
  Data access layer for Address entities.
  """

  @staticmethod
  async def get_by_id(db: AsyncSession, address_id: uuid.UUID) -> Optional[Address]:
    """Load one address by its identifier."""

    result = await db.execute(select(Address).where(Address.id == address_id))
    return result.scalar_one_or_none()

  @staticmethod
  def add(db: AsyncSession, address: Address) -> None:
    """Stages an address entity for insertion or update."""
    db.add(address)
    
  @staticmethod
  async def delete(db: AsyncSession, address: Address) -> None:
    """Directly deletes an address from the database."""
    await db.delete(address)