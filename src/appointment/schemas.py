"""Request and response contracts for appointment slots and bookings."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from src.appointment.domain import (
  AppointmentAction,
  AppointmentSlotStatus,
  AppointmentStatus,
)
from src.core.request_models import StrictRequestModel
from src.core.validation import NormalizedOptionalText


def _require_timezone(value: datetime) -> datetime:
  """Reject naive datetimes so every appointment instant is unambiguous."""

  if value.tzinfo is None or value.utcoffset() is None:
    raise ValueError("datetime must include a timezone")
  return value


class AppointmentSlotCreate(StrictRequestModel):
  """One future interval included in a batch creation request."""

  starts_at: datetime
  ends_at: datetime

  @field_validator("starts_at", "ends_at")
  @classmethod
  def validate_timezone(cls, value: datetime) -> datetime:
    return _require_timezone(value)

  @model_validator(mode="after")
  def validate_interval(self) -> "AppointmentSlotCreate":
    if self.ends_at <= self.starts_at:
      raise ValueError("ends_at must be after starts_at")
    return self


class AppointmentSlotBatchCreate(StrictRequestModel):
  """Bounded batch of office slots created in one transaction."""

  slots: list[AppointmentSlotCreate] = Field(..., min_length=1, max_length=100)


class AppointmentSlotResponse(BaseModel):
  """Public or authority representation of one appointment slot."""

  id: UUID
  office_id: UUID
  starts_at: datetime
  ends_at: datetime
  status: AppointmentSlotStatus
  created_at: datetime

  model_config = {"from_attributes": True}


class AppointmentBookRequest(StrictRequestModel):
  """Citizen booking data with an optional related ticket."""

  ticket_id: UUID | None = None
  reason: NormalizedOptionalText = Field(None, max_length=1000)


class AppointmentResponse(BaseModel):
  """Current appointment projection returned to citizens and staff."""

  id: UUID
  current_slot_id: UUID | None
  office_id: UUID
  citizen_id: UUID
  ticket_id: UUID | None = None
  reason: str | None = None
  status: AppointmentStatus
  starts_at: datetime
  ends_at: datetime
  version: int
  created_at: datetime
  updated_at: datetime
  cancelled_at: datetime | None = None
  completed_at: datetime | None = None
  allowed_actions: list[AppointmentAction] = Field(default_factory=list)
