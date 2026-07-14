import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address


class AddressRepository:
  """Read access for office-owned address entities."""

  @staticmethod
  async def get_by_id(db: AsyncSession, address_id: uuid.UUID) -> Optional[Address]:
    result = await db.execute(select(Address).where(Address.id == address_id))
    return result.scalar_one_or_none()

  @staticmethod
  def add(db: AsyncSession, address: Address) -> None:
    db.add(address)
