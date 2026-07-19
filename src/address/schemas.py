from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.request_models import StrictRequestModel
from src.core.validation import (
  NonNullableNormalizedUpdateText,
  NormalizedRequiredText,
)


class AddressCreate(StrictRequestModel):
  """Creates an independent address record owned by another aggregate."""

  street: NormalizedRequiredText = Field(..., min_length=2, max_length=150)
  house_number: NormalizedRequiredText = Field(..., min_length=1, max_length=20)
  zip_code: NormalizedRequiredText = Field(..., min_length=4, max_length=10)
  city: NormalizedRequiredText = Field(..., min_length=2, max_length=100)
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)


class AddressUpdate(StrictRequestModel):
  """Partially updates an address record."""

  street: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=2,
    max_length=150,
  )
  house_number: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=1,
    max_length=20,
  )
  zip_code: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=4,
    max_length=10,
  )
  city: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=2,
    max_length=100,
  )
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)


class AddressResponse(BaseModel):
  id: UUID
  street: str
  house_number: str
  zip_code: str
  city: str
  latitude: Optional[float] = None
  longitude: Optional[float] = None

  model_config = ConfigDict(from_attributes=True)
