from datetime import datetime, time
from enum import Enum
from typing import Annotated, List, Optional
from uuid import UUID

from pydantic import (
  BaseModel,
  BeforeValidator,
  ConfigDict,
  EmailStr,
  Field,
  field_validator,
  model_validator,
)

from src.address.schemas import AddressCreate, AddressResponse, AddressUpdate
from src.core.normalization import (
  normalize_office_name,
  normalize_optional_text,
  normalize_string_list,
  normalize_text,
)
from src.core.schemas import BaseMetadataResponse
from src.user.schemas import ChangeReason


OfficeName = Annotated[
  str,
  BeforeValidator(normalize_office_name),
  Field(min_length=3, max_length=150),
]
OptionalDescription = Annotated[
  Optional[str],
  BeforeValidator(normalize_optional_text),
  Field(max_length=500),
]
OptionalPhone = Annotated[
  Optional[str],
  BeforeValidator(normalize_optional_text),
  Field(max_length=50, pattern=r"^\+?[0-9\s\-()]+$"),
]
ServiceName = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(min_length=2, max_length=100),
]
Services = Annotated[
  list[ServiceName],
  BeforeValidator(normalize_string_list),
  Field(max_length=50),
]


class OpeningInterval(BaseModel):
  start: time
  end: time

  @model_validator(mode="after")
  def validate_interval(self) -> "OpeningInterval":
    if self.start >= self.end:
      raise ValueError("opening interval start must be before end")
    return self


class OpeningHours(BaseModel):
  """Opening intervals per weekday; an empty list means closed."""

  monday: list[OpeningInterval] = Field(default_factory=list, max_length=8)
  tuesday: list[OpeningInterval] = Field(default_factory=list, max_length=8)
  wednesday: list[OpeningInterval] = Field(default_factory=list, max_length=8)
  thursday: list[OpeningInterval] = Field(default_factory=list, max_length=8)
  friday: list[OpeningInterval] = Field(default_factory=list, max_length=8)
  saturday: list[OpeningInterval] = Field(default_factory=list, max_length=8)
  sunday: list[OpeningInterval] = Field(default_factory=list, max_length=8)

  @model_validator(mode="before")
  @classmethod
  def accept_legacy_day_objects(cls, data):
    """Accept data stored before Patch 11 without preserving its redundant flag."""
    if not isinstance(data, dict):
      return data

    converted = dict(data)
    for day, value in converted.items():
      if isinstance(value, dict) and "intervals" in value:
        converted[day] = [] if value.get("closed") else value.get("intervals", [])
    return converted

  @field_validator("*")
  @classmethod
  def validate_day(cls, intervals: list[OpeningInterval]) -> list[OpeningInterval]:
    ordered = sorted(intervals, key=lambda interval: interval.start)
    for previous, current in zip(ordered, ordered[1:]):
      if previous.end > current.start:
        raise ValueError("opening intervals must not overlap")
    return ordered


class OfficeSortField(str, Enum):
  NAME = "name"
  CREATED_AT = "created_at"


class OfficeCreate(BaseModel):
  """Administrative command for creating an office."""

  name: OfficeName
  description: OptionalDescription = None
  contact_email: Optional[EmailStr] = None
  phone: OptionalPhone = None
  services: Services = Field(default_factory=list)
  opening_hours: OpeningHours = Field(default_factory=OpeningHours)
  address: Optional[AddressCreate] = None


class OfficeUpdate(BaseModel):
  """Administrative partial update command for an office."""

  name: Optional[OfficeName] = None
  description: OptionalDescription = None
  contact_email: Optional[EmailStr] = None
  phone: OptionalPhone = None
  services: Optional[Services] = None
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressUpdate] = None
  change_reason: ChangeReason

  @model_validator(mode="before")
  @classmethod
  def reject_null_owned_values(cls, data):
    if isinstance(data, dict):
      for field in ("name", "services", "address", "opening_hours"):
        if field in data and data[field] is None:
          raise ValueError(
            f"{field} cannot be null; omit it or provide a structured value"
          )
    return data


class OfficeDeactivate(BaseModel):
  change_reason: ChangeReason


class OfficeResponse(BaseMetadataResponse):
  id: UUID
  name: str
  description: Optional[str] = None
  contact_email: Optional[str] = None
  phone: Optional[str] = None
  services: List[str]
  opening_hours: OpeningHours = Field(default_factory=OpeningHours)
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
  opening_hours: OpeningHours = Field(default_factory=OpeningHours)
  address_snapshot: Optional[dict] = None
  is_active: bool
  deactivated_at: Optional[datetime] = None
  changed_by_user_id: UUID
  change_reason: str
  valid_from: datetime
  valid_to: datetime

  model_config = ConfigDict(from_attributes=True)
