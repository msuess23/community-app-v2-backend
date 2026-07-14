import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.core.database import Base


class Address(Base):
  """Physical address owned by at most one office."""

  __tablename__ = "addresses"

  id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
  street = Column(String(150), nullable=False)
  house_number = Column(String(20), nullable=False)
  zip_code = Column(String(20), nullable=False)
  city = Column(String(100), nullable=False)
  latitude = Column(Float, nullable=True)
  longitude = Column(Float, nullable=True)
  created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )
  updated_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=lambda: datetime.now(timezone.utc),
    onupdate=lambda: datetime.now(timezone.utc),
    server_default=func.now(),
  )

  office = relationship(
    "Office",
    back_populates="address",
    uselist=False,
  )

  __table_args__ = (
    CheckConstraint("btrim(street) <> ''", name="ck_addresses_street_not_blank"),
    CheckConstraint(
      "btrim(house_number) <> ''",
      name="ck_addresses_house_number_not_blank",
    ),
    CheckConstraint("btrim(zip_code) <> ''", name="ck_addresses_zip_code_not_blank"),
    CheckConstraint("btrim(city) <> ''", name="ck_addresses_city_not_blank"),
    CheckConstraint(
      "(latitude IS NULL AND longitude IS NULL) OR "
      "(latitude IS NOT NULL AND longitude IS NOT NULL)",
      name="ck_addresses_coordinates_complete",
    ),
    CheckConstraint(
      "latitude IS NULL OR latitude BETWEEN -90 AND 90",
      name="ck_addresses_latitude_range",
    ),
    CheckConstraint(
      "longitude IS NULL OR longitude BETWEEN -180 AND 180",
      name="ck_addresses_longitude_range",
    ),
  )
