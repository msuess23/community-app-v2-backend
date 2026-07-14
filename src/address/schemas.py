from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from src.core.normalization import normalize_text


Street = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(min_length=2, max_length=150),
]
HouseNumber = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(min_length=1, max_length=20),
]
ZipCode = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(min_length=3, max_length=20),
]
City = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(min_length=2, max_length=100),
]


class AddressCreate(BaseModel):
  """Schema for a new address owned by exactly one office."""

  street: Street
  house_number: HouseNumber
  zip_code: ZipCode
  city: City
  latitude: Optional[float] = Field(
    None,
    ge=-90.0,
    le=90.0,
    description="Latitude in decimal degrees",
  )
  longitude: Optional[float] = Field(
    None,
    ge=-180.0,
    le=180.0,
    description="Longitude in decimal degrees",
  )


class AddressUpdate(BaseModel):
  """Partial update for an office-owned address."""

  street: Optional[Street] = None
  house_number: Optional[HouseNumber] = None
  zip_code: Optional[ZipCode] = None
  city: Optional[City] = None
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

  @model_validator(mode="before")
  @classmethod
  def reject_null_required_fields(cls, data):
    if isinstance(data, dict):
      for field in ("street", "house_number", "zip_code", "city"):
        if field in data and data[field] is None:
          raise ValueError(f"{field} cannot be null")
    return data


class AddressResponse(BaseModel):
  id: UUID
  street: str
  house_number: str
  zip_code: str
  city: str
  latitude: Optional[float] = None
  longitude: Optional[float] = None

  model_config = ConfigDict(from_attributes=True)
