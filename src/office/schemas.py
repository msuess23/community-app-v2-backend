import re
from datetime import datetime, time
from itertools import pairwise
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


def _normalize_opening_hours(value: str | None) -> str | None:
  """Normalize and validate one opening-hours value."""

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
  for previous, current in pairwise(intervals):
    if previous[1] > current[0]:
      raise ValueError("opening-hours intervals must not overlap")

  return ", ".join(item[2] for item in intervals)


class OpeningHours(StrictRequestModel):
  """Validate normalized opening-hour values for every weekday."""

  monday: str | None = None
  tuesday: str | None = None
  wednesday: str | None = None
  thursday: str | None = None
  friday: str | None = None
  saturday: str | None = None
  sunday: str | None = None

  @field_validator("*")
  @classmethod
  def validate_day(cls, value: str | None) -> str | None:
    """Validate one weekday opening-hours expression."""

    return _normalize_opening_hours(value)


class OfficeBase(StrictRequestModel):
  """Define fields shared by office creation and response schemas."""

  name: NormalizedRequiredText = Field(..., min_length=3, max_length=150)
  description: NormalizedOptionalText = Field(None, max_length=1000)
  contact_email: EmailStr | None = None
  phone: NormalizedOptionalText = Field(
    None,
    max_length=50,
    pattern=r"^\+?[0-9\s\-\(\)]+$",
  )
  services: list[str] = Field(default_factory=list, max_length=50)
  opening_hours: OpeningHours | None = None

  @field_validator("services")
  @classmethod
  def normalize_services(cls, values: list[str]) -> list[str]:
    """Normalize and deduplicate the configured office services."""

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
  """Validate the payload used to create an office."""

  address: AddressCreate | None = None


class OfficeUpdate(StrictRequestModel):
  """Validate a partial office update payload."""

  name: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=3,
    max_length=150,
  )
  description: NormalizedOptionalText = Field(None, max_length=1000)
  contact_email: EmailStr | None = None
  phone: NormalizedOptionalText = Field(
    None,
    max_length=50,
    pattern=r"^\+?[0-9\s\-\(\)]+$",
  )
  services: list[str] | None = Field(None, max_length=50)
  opening_hours: OpeningHours | None = None
  address: AddressUpdate | None = None
  change_reason: ChangeReason

  @field_validator("services", mode="before")
  @classmethod
  def reject_null_services(cls, value: object) -> object:
    """Reject explicit null for the non-nullable service collection."""

    if value is None:
      raise ValueError("services cannot be null")
    return value

  @field_validator("services")
  @classmethod
  def normalize_services(cls, values: list[str] | None) -> list[str] | None:
    """Normalize and deduplicate updated office services."""

    return OfficeBase.normalize_services(values) if values is not None else None


class OfficeDeactivateRequest(StrictRequestModel):
  """Validate the audit reason for office deactivation."""

  change_reason: ChangeReason


class OfficeResponse(BaseMetadataResponse):
  """Serialize an office and its optional owned address."""

  id: UUID
  name: str
  description: str | None = None
  contact_email: str | None = None
  phone: str | None = None
  services: list[str]
  opening_hours: OpeningHours | None = None
  address: AddressResponse | None = None

  model_config = ConfigDict(from_attributes=True)


class OfficeHistoryResponse(BaseModel):
  """Serialize one immutable office history snapshot."""

  id: UUID
  office_id: UUID
  name: str
  description: str | None = None
  contact_email: str | None = None
  phone: str | None = None
  services: list[str] = Field(default_factory=list)
  opening_hours: dict = Field(default_factory=dict)
  address_snapshot: AddressSnapshot | None = None
  is_active: bool
  changed_by_user_id: UUID
  change_reason: str
  changed_at: datetime

  model_config = ConfigDict(from_attributes=True)
