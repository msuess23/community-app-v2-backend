"""Enums used by appointment slots, aggregates and API filters."""

from __future__ import annotations

import enum


class AppointmentSlotStatus(str, enum.Enum):
  """Lifecycle of one offered office appointment slot."""

  AVAILABLE = "AVAILABLE"
  BOOKED = "BOOKED"
  INACTIVE = "INACTIVE"
  CONSUMED = "CONSUMED"


class AppointmentStatus(str, enum.Enum):
  """Citizen-visible lifecycle of a booked appointment."""

  SCHEDULED = "SCHEDULED"
  CANCELLED = "CANCELLED"
  COMPLETED = "COMPLETED"
  NO_SHOW = "NO_SHOW"


class AppointmentEventType(str, enum.Enum):
  """Append-only changes supported by the appointment aggregate."""

  APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"
  APPOINTMENT_RESCHEDULED = "APPOINTMENT_RESCHEDULED"
  APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
  APPOINTMENT_COMPLETED = "APPOINTMENT_COMPLETED"
  APPOINTMENT_MARKED_NO_SHOW = "APPOINTMENT_MARKED_NO_SHOW"
  DOCUMENT_VERSION_ADDED = "DOCUMENT_VERSION_ADDED"


class AppointmentAction(str, enum.Enum):
  """Commands that may later be exposed by an appointment response."""

  RESCHEDULE = "RESCHEDULE"
  CANCEL = "CANCEL"
  COMPLETE = "COMPLETE"
  MARK_NO_SHOW = "MARK_NO_SHOW"


class AppointmentDocumentType(str, enum.Enum):
  """Small controlled vocabulary for versioned appointment PDFs."""

  CONFIRMATION = "CONFIRMATION"
  FORM = "FORM"
  NOTICE = "NOTICE"
  PROTOCOL = "PROTOCOL"
  OTHER = "OTHER"


class AppointmentSortField(str, enum.Enum):
  """Allowed sort columns for appointment list endpoints."""

  STARTS_AT = "starts_at"
  CREATED_AT = "created_at"
  STATUS = "status"


class AppointmentSlotSortField(str, enum.Enum):
  """Allowed sort columns for slot list endpoints."""

  STARTS_AT = "starts_at"
  CREATED_AT = "created_at"
  STATUS = "status"
