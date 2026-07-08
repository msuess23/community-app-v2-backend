from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID

class AddressCreate(BaseModel):
  """Schema for creating a new address attached to another entity."""
  street: str = Field(..., min_length=2, max_length=255)
  house_number: str = Field(..., min_length=1, max_length=50)
  zip_code: str = Field(..., min_length=4, max_length=20)
  city: str = Field(..., min_length=2, max_length=255)
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Latitude in decimal degrees")
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Longitude in decimal degrees")

class AddressUpdate(BaseModel):
  """Schema for updating an existing address. All fields are optional (PATCH behavior)."""
  street: Optional[str] = Field(None, min_length=2, max_length=255)
  house_number: Optional[str] = Field(None, min_length=1, max_length=50)
  zip_code: Optional[str] = Field(None, min_length=4, max_length=20)
  city: Optional[str] = Field(None, min_length=2, max_length=255)
  latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
  longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

class AddressResponse(BaseModel):
  """Schema for returning address data to the client."""
  id: UUID
  street: str
  house_number: str
  zip_code: str
  city: str
  latitude: Optional[float] = None
  longitude: Optional[float] = None
  
  model_config = ConfigDict(from_attributes=True)