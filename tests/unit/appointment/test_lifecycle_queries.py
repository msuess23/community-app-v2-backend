"""Allowed-action and event-visibility tests for appointment queries."""

import uuid
from datetime import datetime, timedelta, timezone

from src.appointment.domain import AppointmentAction, AppointmentEventType, AppointmentStatus
from src.appointment.models import Appointment, AppointmentEvent
from src.appointment.service import AppointmentService
from src.user.models import Role, User


def _user(role: Role, *, office_id=None, user_id=None) -> User:
  return User(
    id=user_id or uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="hash",
    first_name="Query",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _appointment(citizen_id, office_id, starts_at) -> Appointment:
  return Appointment(
    id=uuid.uuid4(),
    current_slot_id=uuid.uuid4(),
    office_id=office_id,
    citizen_id=citizen_id,
    status=AppointmentStatus.SCHEDULED,
    starts_at=starts_at,
    ends_at=starts_at + timedelta(minutes=30),
    version=1,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
  )


def test_allowed_actions_change_at_appointment_start() -> None:
  now = datetime.now(timezone.utc)
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  officer = _user(Role.OFFICER, office_id=office_id)
  future = _appointment(citizen.id, office_id, now + timedelta(hours=1))
  started = _appointment(citizen.id, office_id, now - timedelta(minutes=1))

  assert AppointmentService.allowed_actions(future, citizen, now=now) == [
    AppointmentAction.RESCHEDULE,
    AppointmentAction.CANCEL,
  ]
  assert AppointmentService.allowed_actions(started, citizen, now=now) == []
  assert AppointmentService.allowed_actions(started, officer, now=now) == [
    AppointmentAction.COMPLETE,
    AppointmentAction.MARK_NO_SHOW,
  ]


def test_citizen_event_response_hides_actor_identifier() -> None:
  event = AppointmentEvent(
    id=uuid.uuid4(),
    appointment_id=uuid.uuid4(),
    sequence_number=1,
    event_type=AppointmentEventType.APPOINTMENT_BOOKED,
    actor_user_id=uuid.uuid4(),
    occurred_at=datetime.now(timezone.utc),
    payload={},
  )

  public = AppointmentService.event_response(event, include_actor=False)
  internal = AppointmentService.event_response(event, include_actor=True)

  assert public.actor_user_id is None
  assert internal.actor_user_id == event.actor_user_id


def test_citizen_document_event_hides_storage_key() -> None:
  from src.appointment.domain import AppointmentEventType
  from src.appointment.models import AppointmentEvent
  from src.appointment.service import AppointmentService

  event = AppointmentEvent(
    id=uuid.uuid4(),
    appointment_id=uuid.uuid4(),
    sequence_number=2,
    event_type=AppointmentEventType.DOCUMENT_VERSION_ADDED,
    actor_user_id=uuid.uuid4(),
    occurred_at=datetime.now(timezone.utc),
    payload={
      "document_group_id": str(uuid.uuid4()),
      "document_version_id": str(uuid.uuid4()),
      "storage_key": "private/path/document.pdf",
      "visible_to_citizen": True,
    },
  )

  response = AppointmentService.event_response(event, include_actor=False)

  assert response.actor_user_id is None
  assert "storage_key" not in response.payload
