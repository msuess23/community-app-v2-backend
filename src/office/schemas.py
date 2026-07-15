from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.address.schemas import AddressCreate, AddressResponse, AddressUpdate
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
  """Schema for creating a new office."""

  name: str = Field(..., min_length=3, max_length=150)
  description: Optional[str] = Field(None, max_length=500)
  contact_email: Optional[EmailStr] = None
  phone: Optional[str] = Field(None, max_length=50, pattern=r"^\+?[0-9\s\-\(\)]+$")
  services: List[str] = Field(default_factory=list)
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressCreate] = None


class OfficeUpdate(BaseModel):
  """Schema for a partial administrative office update."""

  name: Optional[str] = Field(None, min_length=3, max_length=150)
  description: Optional[str] = Field(None, max_length=500)
  contact_email: Optional[EmailStr] = None
  phone: Optional[str] = Field(None, max_length=50, pattern=r"^\+?[0-9\s\-\(\)]+$")
  services: Optional[List[str]] = None
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressUpdate] = None
  change_reason: str = Field(..., min_length=3, max_length=500)

  @field_validator("change_reason")
  @classmethod
  def normalize_change_reason(cls, value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 3:
      raise ValueError("change_reason must contain at least 3 characters")
    return normalized


class OfficeDeactivateRequest(BaseModel):
  change_reason: str = Field(..., min_length=3, max_length=500)

  @field_validator("change_reason")
  @classmethod
  def normalize_change_reason(cls, value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 3:
      raise ValueError("change_reason must contain at least 3 characters")
    return normalized


class OfficeResponse(BaseMetadataResponse):
  id: UUID
  name: str
  description: Optional[str] = None
  contact_email: Optional[str] = None
  phone: Optional[str] = None
  services: List[str]
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressResponse] = None

  model_config = ConfigDict(from_attributes=True)


class OfficeHistoryResponse(BaseModel):
  id: UUID
  office_id: UUID
  name: str
  description: Optional[str] = None
  contact_email: Optional[str] = None
  phone: Optional[str] = None
  services: list[str] = Field(default_factory=list)
  opening_hours: dict = Field(default_factory=dict)
  address_snapshot: Optional[str] = None
  is_active: bool
  changed_by_user_id: UUID
  change_reason: str
  changed_at: datetime

  model_config = ConfigDict(from_attributes=True)
