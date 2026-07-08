import uuid
from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone

from src.core.database import Base

class Address(Base):
  """
  Represents a physical location including geographical coordinates.
  Used as a related entity for Offices, Tickets, and potentially Users.
  """
  __tablename__ = "addresses"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  street = Column(String, nullable=False)
  house_number = Column(String, nullable=False)
  zip_code = Column(String, nullable=False)
  city = Column(String, nullable=False)
  
  # Coordinates are optional but highly recommended for the map features
  latitude = Column(Float, nullable=True)
  longitude = Column(Float, nullable=True)
  
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))