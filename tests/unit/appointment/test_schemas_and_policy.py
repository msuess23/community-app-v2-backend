"""Validation and authorization tests for appointment boundaries."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import AppointmentStatus
from src.appointment.models import Appointment
from src.appointment.schemas import AppointmentSlotBatchCreate, AppointmentSlotCreate
from src.user.models import Role, User


def _user(role: Role, *, office_id=None) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="hash",
    first_name="Test",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=True,
  )


def test_slot_schema_rejects_naive_and_reversed_datetimes() -> None:
  now = datetime.now(timezone.utc)

  with pytest.raises(ValidationError):
    AppointmentSlotCreate(
      starts_at=datetime.now(),
      ends_at=datetime.now() + timedelta(minutes=30),
    )

  with pytest.raises(ValidationError):
    AppointmentSlotCreate(
      starts_at=now + timedelta(hours=1),
      ends_at=now,
    )


def test_slot_batch_rejects_unknown_fields() -> None:
  now = datetime.now(timezone.utc)

  with pytest.raises(ValidationError):
    AppointmentSlotBatchCreate.model_validate(
      {
        "slots": [
          {
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=1, minutes=30)).isoformat(),
          }
        ],
        "office": "unexpected",
      }
    )


def test_access_policy_limits_authority_access_to_own_office() -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  officer = _user(Role.OFFICER, office_id=office_id)
  foreign_manager = _user(Role.MANAGER, office_id=uuid.uuid4())
  appointment = Appointment(
    id=uuid.uuid4(),
    current_slot_id=uuid.uuid4(),
    office_id=office_id,
    citizen_id=citizen.id,
    status=AppointmentStatus.SCHEDULED,
    starts_at=datetime.now(timezone.utc) + timedelta(days=1),
    ends_at=datetime.now(timezone.utc) + timedelta(days=1, minutes=30),
    version=1,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
  )

  assert AppointmentAccessPolicy.can_view(appointment, citizen)
  assert AppointmentAccessPolicy.can_view(appointment, officer)
  assert not AppointmentAccessPolicy.can_view(appointment, foreign_manager)


def test_appointment_models_keep_slot_and_event_stream_unique() -> None:
  from src.appointment.models import AppointmentEvent

  current_slot = Appointment.__table__.c.current_slot_id
  assert current_slot.unique is True
  assert Appointment.__table__.c.ticket_id.foreign_keys
  assert any(
    constraint.name == "uq_appointment_events_appointment_sequence"
    for constraint in AppointmentEvent.__table__.constraints
  )
