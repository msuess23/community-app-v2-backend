import re
from datetime import datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.address.schemas import AddressCreate, AddressResponse, AddressUpdate
from src.address.snapshot import AddressSnapshot
from src.core.request_models import StrictRequestModel
from src.core.schemas import BaseMetadataResponse
from src.core.validation import (
  ChangeReason,
  NonNullableNormalizedUpdateText,
  NormalizedOptionalText,
  NormalizedRequiredText,
  normalize_required_text,
)


_OPENING_INTERVAL = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")


def _normalize_opening_hours(value: Optional[str]) -> Optional[str]:
  if value is None:
    return None

  normalized = " ".join(value.strip().split())
  if not normalized:
    return None
  if normalized.lower() in {"geschlossen", "closed"}:
    return "geschlossen"

  intervals: list[tuple[time, time, str]] = []
  for raw_interval in normalized.split(","):
    interval = raw_interval.strip().replace(" ", "")
    match = _OPENING_INTERVAL.fullmatch(interval)
    if not match:
      raise ValueError("opening hours must use HH:MM-HH:MM intervals")
    start_hour, start_minute, end_hour, end_minute = map(int, match.groups())
    try:
      start = time(start_hour, start_minute)
      end = time(end_hour, end_minute)
    except ValueError as exc:
      raise ValueError("opening hours contain an invalid time") from exc
    if start >= end:
      raise ValueError("opening-hours interval start must be before end")
    intervals.append((start, end, interval))

  intervals.sort(key=lambda item: item[0])
  for previous, current in zip(intervals, intervals[1:]):
    if previous[1] > current[0]:
      raise ValueError("opening-hours intervals must not overlap")

  return ", ".join(item[2] for item in intervals)


class OpeningHours(StrictRequestModel):
  monday: Optional[str] = None
  tuesday: Optional[str] = None
  wednesday: Optional[str] = None
  thursday: Optional[str] = None
  friday: Optional[str] = None
  saturday: Optional[str] = None
  sunday: Optional[str] = None

  @field_validator("*")
  @classmethod
  def validate_day(cls, value: Optional[str]) -> Optional[str]:
    return _normalize_opening_hours(value)


class OfficeBase(StrictRequestModel):
  name: NormalizedRequiredText = Field(..., min_length=3, max_length=150)
  description: NormalizedOptionalText = Field(None, max_length=1000)
  contact_email: Optional[EmailStr] = None
  phone: NormalizedOptionalText = Field(
    None,
    max_length=50,
    pattern=r"^\+?[0-9\s\-\(\)]+$",
  )
  services: list[str] = Field(default_factory=list, max_length=50)
  opening_hours: Optional[OpeningHours] = None

  @field_validator("services")
  @classmethod
  def normalize_services(cls, values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
      normalized = normalize_required_text(value)
      if len(normalized) > 100:
        raise ValueError("service entries must not exceed 100 characters")
      key = normalized.casefold()
      if key not in seen:
        result.append(normalized)
        seen.add(key)
    return result


class OfficeCreate(OfficeBase):
  address: Optional[AddressCreate] = None


class OfficeUpdate(StrictRequestModel):
  name: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=3,
    max_length=150,
  )
  description: NormalizedOptionalText = Field(None, max_length=1000)
  contact_email: Optional[EmailStr] = None
  phone: NormalizedOptionalText = Field(
    None,
    max_length=50,
    pattern=r"^\+?[0-9\s\-\(\)]+$",
  )
  services: Optional[list[str]] = Field(None, max_length=50)
  opening_hours: Optional[OpeningHours] = None
  address: Optional[AddressUpdate] = None
  change_reason: ChangeReason

  @field_validator("services", mode="before")
  @classmethod
  def reject_null_services(cls, value: object) -> object:
    if value is None:
      raise ValueError("services cannot be null")
    return value

  @field_validator("services")
  @classmethod
  def normalize_services(cls, values: Optional[list[str]]) -> Optional[list[str]]:
    return OfficeBase.normalize_services(values) if values is not None else None


class OfficeDeactivateRequest(StrictRequestModel):
  change_reason: ChangeReason


class OfficeResponse(BaseMetadataResponse):
  id: UUID
  name: str
  description: Optional[str] = None
  contact_email: Optional[str] = None
  phone: Optional[str] = None
  services: list[str]
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
  address_snapshot: Optional[AddressSnapshot] = None
  is_active: bool
  changed_by_user_id: UUID
  change_reason: str
  changed_at: datetime

  model_config = ConfigDict(from_attributes=True)
