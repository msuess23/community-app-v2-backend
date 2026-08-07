"""Validated payload schemas for appointment event streams."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter

from src.appointment.domain.enums import (
  AppointmentDocumentType,
  AppointmentEventType,
)
from src.core.validation import NormalizedOptionalText, NormalizedRequiredText


class AppointmentBookedPayload(BaseModel):
  """Complete initial state required to rebuild a booking."""

  slot_id: UUID
  office_id: UUID
  citizen_id: UUID
  ticket_id: UUID | None = None
  reason: NormalizedOptionalText = Field(None, max_length=1000)
  starts_at: datetime
  ends_at: datetime


class AppointmentRescheduledPayload(BaseModel):
  """Previous and resulting slot data for one reschedule operation."""

  previous_slot_id: UUID
  new_slot_id: UUID
  previous_starts_at: datetime
  previous_ends_at: datetime
  new_starts_at: datetime
  new_ends_at: datetime
  reason: NormalizedRequiredText = Field(..., min_length=3, max_length=500)


class AppointmentCancelledPayload(BaseModel):
  """Reason recorded when a scheduled appointment is cancelled."""

  slot_id: UUID
  reason: NormalizedRequiredText = Field(..., min_length=3, max_length=500)


class AppointmentCompletedPayload(BaseModel):
  """Optional authority note recorded when an appointment is completed."""

  comment: NormalizedOptionalText = Field(None, max_length=1000)


class AppointmentMarkedNoShowPayload(BaseModel):
  """Optional authority note recorded for a citizen no-show."""

  comment: NormalizedOptionalText = Field(None, max_length=1000)


class DocumentVersionAddedPayload(BaseModel):
  """Immutable metadata for one versioned appointment document."""

  document_group_id: UUID
  document_version_id: UUID
  version_number: int = Field(ge=1)
  document_type: AppointmentDocumentType
  storage_key: str = Field(min_length=1, max_length=500)
  original_filename: str = Field(min_length=1, max_length=255)
  mime_type: str = Field(min_length=1, max_length=100)
  size_bytes: int = Field(ge=1)
  visible_to_citizen: bool
  replaced_version_id: UUID | None = None


AppointmentEventPayload = (
  AppointmentBookedPayload
  | AppointmentRescheduledPayload
  | AppointmentCancelledPayload
  | AppointmentCompletedPayload
  | AppointmentMarkedNoShowPayload
  | DocumentVersionAddedPayload
)


_EVENT_PAYLOAD_TYPES: dict[AppointmentEventType, type[BaseModel]] = {
  AppointmentEventType.APPOINTMENT_BOOKED: AppointmentBookedPayload,
  AppointmentEventType.APPOINTMENT_RESCHEDULED: AppointmentRescheduledPayload,
  AppointmentEventType.APPOINTMENT_CANCELLED: AppointmentCancelledPayload,
  AppointmentEventType.APPOINTMENT_COMPLETED: AppointmentCompletedPayload,
  AppointmentEventType.APPOINTMENT_MARKED_NO_SHOW: AppointmentMarkedNoShowPayload,
  AppointmentEventType.DOCUMENT_VERSION_ADDED: DocumentVersionAddedPayload,
}


def validate_appointment_event_payload(
  event_type: AppointmentEventType,
  payload: BaseModel | dict[str, Any],
) -> AppointmentEventPayload:
  """Validate an event payload against the schema assigned to its type."""

  return TypeAdapter(_EVENT_PAYLOAD_TYPES[event_type]).validate_python(payload)
