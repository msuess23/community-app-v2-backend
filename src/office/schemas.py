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


class DaySchedule(BaseModel):
  closed: bool = True
  intervals: list[OpeningInterval] = Field(default_factory=list, max_length=8)

  @model_validator(mode="before")
  @classmethod
  def infer_closed(cls, data):
    if isinstance(data, dict) and "closed" not in data:
      data = dict(data)
      data["closed"] = not bool(data.get("intervals"))
    return data

  @model_validator(mode="after")
  def validate_schedule(self) -> "DaySchedule":
    if self.closed and self.intervals:
      raise ValueError("a closed day cannot contain opening intervals")
    if not self.closed and not self.intervals:
      raise ValueError("an open day requires at least one opening interval")

    ordered = sorted(self.intervals, key=lambda interval: interval.start)
    for previous, current in zip(ordered, ordered[1:]):
      if previous.end > current.start:
        raise ValueError("opening intervals must not overlap")
    self.intervals = ordered
    return self


class OpeningHours(BaseModel):
  monday: DaySchedule = Field(default_factory=DaySchedule)
  tuesday: DaySchedule = Field(default_factory=DaySchedule)
  wednesday: DaySchedule = Field(default_factory=DaySchedule)
  thursday: DaySchedule = Field(default_factory=DaySchedule)
  friday: DaySchedule = Field(default_factory=DaySchedule)
  saturday: DaySchedule = Field(default_factory=DaySchedule)
  sunday: DaySchedule = Field(default_factory=DaySchedule)


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
  valid_to: Optional[datetime] = None

  model_config = ConfigDict(from_attributes=True)
