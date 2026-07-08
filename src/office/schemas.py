from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from src.address.schemas import AddressCreate, AddressUpdate, AddressResponse
from src.core.schemas import BaseMetadataResponse

class OpeningHours(BaseModel):
  """Structured representation of opening hours per weekday."""
  monday: Optional[str] = Field(None, description="e.g. '08:00-12:00, 13:00-16:00'")
  tuesday: Optional[str] = None
  wednesday: Optional[str] = None
  thursday: Optional[str] = None
  friday: Optional[str] = None
  saturday: Optional[str] = None
  sunday: Optional[str] = Field(None, description="Usually 'geschlossen'")


class OfficeCreate(BaseModel):
  """
  Schema for creating a new office.
  Restricted to administrators.
  """
  name: str = Field(..., min_length=3, max_length=150, description="Official name of the office/department")
  description: Optional[str] = Field(None, max_length=500, description="Optional details about the office's responsibilities")
  contact_email: Optional[EmailStr] = None
  phone: Optional[str] = Field(None, max_length=50, pattern=r"^\+?[0-9\s\-\(\)]+$")
  services: List[str] = Field(default_factory=list, description="List of services offered")
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressCreate] = None


class OfficeUpdate(BaseModel):
  """
  Schema for updating an existing office.
  All fields are optional to allow partial updates (PATCH).
  """
  name: Optional[str] = Field(None, min_length=3, max_length=150)
  description: Optional[str] = Field(None, max_length=500)
  contact_email: Optional[EmailStr] = None
  phone: Optional[str] = Field(None, max_length=50, pattern=r"^\+?[0-9\s\-\(\)]+$")
  services: Optional[List[str]] = None
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressUpdate] = None


class OfficeResponse(BaseMetadataResponse):
  """
  Schema for returning office data to the client.
  """
  id: UUID
  name: str
  description: Optional[str] = None
  contact_email: Optional[str] = None
  phone: Optional[str] = None
  services: List[str]
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressResponse] = None
  model_config = ConfigDict(from_attributes=True)