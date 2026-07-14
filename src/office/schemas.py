from datetime import datetime
from typing import Annotated, Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from src.address.schemas import AddressCreate, AddressResponse, AddressUpdate
from src.core.normalization import normalize_office_name
from src.core.schemas import BaseMetadataResponse
from src.user.schemas import ChangeReason


OfficeName = Annotated[
  str,
  BeforeValidator(normalize_office_name),
  Field(min_length=3, max_length=150),
]


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
  """Administrative command for creating an office."""

  name: OfficeName
  description: Optional[str] = Field(None, max_length=500)
  contact_email: Optional[EmailStr] = None
  phone: Optional[str] = Field(None, max_length=50, pattern=r"^\+?[0-9\s\-\(\)]+$")
  services: List[str] = Field(default_factory=list)
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressCreate] = None


class OfficeUpdate(BaseModel):
  """Administrative partial update command for an office."""

  name: Optional[OfficeName] = None
  description: Optional[str] = Field(None, max_length=500)
  contact_email: Optional[EmailStr] = None
  phone: Optional[str] = Field(None, max_length=50, pattern=r"^\+?[0-9\s\-\(\)]+$")
  services: Optional[List[str]] = None
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressUpdate] = None
  change_reason: ChangeReason


class OfficeDeactivate(BaseModel):
  change_reason: ChangeReason


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
  opening_hours: dict[str, Any] = Field(default_factory=dict)
  address_snapshot: Optional[dict[str, Any]] = None
  is_active: bool
  deactivated_at: Optional[datetime] = None
  changed_by_user_id: UUID
  change_reason: str
  valid_from: datetime
  valid_to: Optional[datetime] = None

  model_config = ConfigDict(from_attributes=True)
