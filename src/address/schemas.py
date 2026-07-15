from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_required(value: str) -> str:
  normalized = " ".join(value.split())
  if not normalized:
    raise ValueError("value must not be blank")
  return normalized


class AddressCreate(BaseModel):
  """Creates an independent address record owned by another aggregate."""

  street: str = Field(..., min_length=2, max_length=150)
  house_number: str = Field(..., min_length=1, max_length=20)
  zip_code: str = Field(..., min_length=4, max_length=10)
  city: str = Field(..., min_length=2, max_length=100)
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

  @field_validator("street", "house_number", "zip_code", "city")
  @classmethod
  def normalize_strings(cls, value: str) -> str:
    return _normalize_required(value)


class AddressUpdate(BaseModel):
  """Partially updates an address record."""

  street: Optional[str] = Field(None, min_length=2, max_length=150)
  house_number: Optional[str] = Field(None, min_length=1, max_length=20)
  zip_code: Optional[str] = Field(None, min_length=4, max_length=10)
  city: Optional[str] = Field(None, min_length=2, max_length=100)
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

  @field_validator("street", "house_number", "zip_code", "city")
  @classmethod
  def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
    return _normalize_required(value) if value is not None else None


class AddressResponse(BaseModel):
  id: UUID
  street: str
  house_number: str
  zip_code: str
  city: str
  latitude: Optional[float] = None
  longitude: Optional[float] = None

  model_config = ConfigDict(from_attributes=True)


class AddressHistorySnapshot(BaseModel):
  street: str
  house_number: str
  zip_code: str
  city: str
  latitude: Optional[float] = None
  longitude: Optional[float] = None
