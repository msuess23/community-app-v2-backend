"""Requests and responses for classical Info CRUD."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.address.schemas import AddressCreate, AddressResponse, AddressUpdate
from src.core.request_models import StrictRequestModel
from src.core.validation import (
  NonNullableNormalizedUpdateText,
  NormalizedOptionalText,
  NormalizedRequiredText,
)
from src.info.models import InfoCategory, InfoStatus
from src.media.schemas import ImageMetadataResponse


def _require_timezone(value: datetime) -> datetime:
  if value.tzinfo is None or value.utcoffset() is None:
    raise ValueError("datetime must include a timezone")
  return value


class InfoCreateRequest(StrictRequestModel):
  """Create one time-bounded information notice."""

  title: NormalizedRequiredText = Field(..., min_length=3, max_length=255)
  description: NormalizedOptionalText = Field(None, max_length=5000)
  category: InfoCategory
  office_id: UUID | None = None
  address: AddressCreate | None = None
  starts_at: datetime
  ends_at: datetime

  @field_validator("starts_at", "ends_at")
  @classmethod
  def validate_timezone(cls, value: datetime) -> datetime:
    return _require_timezone(value)

  @model_validator(mode="after")
  def validate_interval(self) -> "InfoCreateRequest":
    if self.ends_at <= self.starts_at:
      raise ValueError("ends_at must be after starts_at")
    return self


class InfoUpdateRequest(StrictRequestModel):
  """Partially update the same Info row without creating a revision."""

  title: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=3,
    max_length=255,
  )
  description: NormalizedOptionalText = Field(None, max_length=5000)
  category: InfoCategory | None = None
  office_id: UUID | None = None
  address: AddressUpdate | None = None
  starts_at: datetime | None = None
  ends_at: datetime | None = None

  @field_validator("category", mode="before")
  @classmethod
  def reject_null_category(cls, value: object) -> object:
    if value is None:
      raise ValueError("category cannot be null")
    return value

  @field_validator("starts_at", "ends_at", mode="before")
  @classmethod
  def reject_null_datetimes(cls, value: object) -> object:
    if value is None:
      raise ValueError("starts_at and ends_at cannot be null")
    return value

  @field_validator("starts_at", "ends_at")
  @classmethod
  def validate_timezone(cls, value: datetime | None) -> datetime | None:
    return _require_timezone(value) if value is not None else None


class InfoStatusCreateRequest(StrictRequestModel):
  """Append one simple status message and update the current status."""

  status: InfoStatus
  message: NormalizedOptionalText = Field(None, max_length=1000)


class InfoStatusResponse(BaseModel):
  """Public status history item without an internal actor identifier."""

  id: UUID
  status: InfoStatus
  message: str | None = None
  created_at: datetime

  model_config = ConfigDict(from_attributes=True)


class InfoImageResponse(ImageMetadataResponse):
  """Public metadata for one current image owned by an Info."""

  info_id: UUID


class InfoResponse(BaseModel):
  """Public representation of one current Info CRUD row."""

  id: UUID
  title: str
  description: str | None = None
  category: InfoCategory
  office_id: UUID | None = None
  address: AddressResponse | None = None
  created_at: datetime
  updated_at: datetime
  starts_at: datetime
  ends_at: datetime
  current_status: InfoStatusResponse
  image_url: str | None = None

  model_config = ConfigDict(from_attributes=True)
