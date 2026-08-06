"""Regression tests for the frontend-ready appointment API contract."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.appointment.domain import AppointmentEventType, AppointmentStatus
from src.appointment.models import Appointment, AppointmentEvent
from src.appointment.repository import AppointmentRepository
from src.appointment.service import AppointmentService
from src.core.exceptions import ForbiddenException, ResourceNotFoundException
from src.office.models import Office
from src.ticket.domain import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.user.models import Role, User
from src.user.repository import UserRepository


def _user(role: Role, *, office_id=None, name: tuple[str, str] = ("Test", "User")) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="hash",
    first_name=name[0],
    last_name=name[1],
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _ticket(citizen_id: uuid.UUID, office_id: uuid.UUID, *, title: str) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid.uuid4(),
    title=title,
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=citizen_id,
    office_id=office_id,
    visibility=TicketVisibility.PUBLIC,
    public_status=TicketStatus.IN_PROGRESS,
    workflow_state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    version=1,
    created_at=now,
    updated_at=now,
  )


def _appointment(
  citizen: User,
  office: Office,
  *,
  ticket: Ticket | None = None,
) -> Appointment:
  starts_at = datetime.now(timezone.utc) + timedelta(days=1)
  appointment = Appointment(
    id=uuid.uuid4(),
    current_slot_id=uuid.uuid4(),
    office_id=office.id,
    citizen_id=citizen.id,
    ticket_id=ticket.id if ticket is not None else None,
    status=AppointmentStatus.SCHEDULED,
    starts_at=starts_at,
    ends_at=starts_at + timedelta(minutes=30),
    version=1,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
  )
  appointment.office = office
  appointment.citizen = citizen
  appointment.ticket = ticket
  return appointment


def test_response_embeds_readable_references_and_ticket_access() -> None:
  office = Office(id=uuid.uuid4(), name="Bauamt", is_active=True)
  citizen = _user(Role.CITIZEN, name=("Ada", "Lovelace"))
  officer = _user(Role.OFFICER, office_id=office.id)
  ticket = _ticket(citizen.id, office.id, title="Linked construction ticket")
  appointment = _appointment(citizen, office, ticket=ticket)

  response = AppointmentService.to_response(appointment, current_user=officer)

  assert response.office.name == "Bauamt"
  assert response.citizen.display_name == "Ada Lovelace"
  assert response.ticket is not None
  assert response.ticket.title == "Linked construction ticket"
  assert response.ticket.can_view is True


def test_citizen_event_response_redacts_internal_outcome_comment() -> None:
  actor = _user(Role.OFFICER, office_id=uuid.uuid4(), name=("Ona", "Officer"))
  event = AppointmentEvent(
    id=uuid.uuid4(),
    appointment_id=uuid.uuid4(),
    sequence_number=4,
    event_type=AppointmentEventType.APPOINTMENT_COMPLETED,
    actor_user_id=actor.id,
    occurred_at=datetime.now(timezone.utc),
    payload={"comment": "Internal assessment"},
  )
  event.actor = actor

  citizen_response = AppointmentService.event_response(event, include_actor=False)
  staff_response = AppointmentService.event_response(event, include_actor=True)

  assert citizen_response.actor_user_id is None
  assert citizen_response.actor is None
  assert "comment" not in citizen_response.payload
  assert staff_response.actor_user_id == actor.id
  assert staff_response.actor is not None
  assert staff_response.actor.display_name == "Ona Officer"
  assert staff_response.payload["comment"] == "Internal assessment"


@pytest.mark.asyncio
async def test_filter_options_are_derived_from_the_staff_office_scope(monkeypatch) -> None:
  office_id = uuid.uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  citizen_a = _user(Role.CITIZEN, name=("Zoe", "Citizen"))
  citizen_b = _user(Role.CITIZEN, name=("Ada", "Citizen"))
  ticket = _ticket(citizen_a.id, office_id, title="Appointment-linked ticket")

  references = AsyncMock(return_value=({citizen_a.id, citizen_b.id}, {ticket.id}))
  monkeypatch.setattr(
    AppointmentRepository,
    "get_internal_filter_reference_ids",
    references,
  )
  monkeypatch.setattr(
    UserRepository,
    "get_by_ids",
    AsyncMock(return_value=[citizen_a, citizen_b]),
  )
  monkeypatch.setattr(
    AppointmentRepository,
    "get_tickets_by_ids",
    AsyncMock(return_value=[ticket]),
  )

  response = await AppointmentService.get_internal_filter_options(
    AsyncMock(),
    current_user=manager,
  )

  assert [item.display_name for item in response.citizens] == [
    "Ada Citizen",
    "Zoe Citizen",
  ]
  assert [item.title for item in response.tickets] == ["Appointment-linked ticket"]
  assert references.await_args.kwargs["office_id"] == office_id


@pytest.mark.asyncio
async def test_filter_options_reject_users_without_an_appointment_office() -> None:
  with pytest.raises(ForbiddenException):
    await AppointmentService.get_internal_filter_options(
      AsyncMock(),
      current_user=_user(Role.DISPATCHER),
    )


@pytest.mark.asyncio
async def test_hidden_appointment_detail_uses_not_found(monkeypatch) -> None:
  office = Office(id=uuid.uuid4(), name="Bauamt", is_active=True)
  citizen = _user(Role.CITIZEN)
  foreign_officer = _user(Role.OFFICER, office_id=uuid.uuid4())
  appointment = _appointment(citizen, office)
  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )

  with pytest.raises(ResourceNotFoundException) as exc:
    await AppointmentService.get_appointment(
      AsyncMock(),
      appointment.id,
      foreign_officer,
    )

  assert exc.value.error_code == "APPOINTMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_internal_search_covers_citizen_contact_and_linked_ticket(monkeypatch) -> None:
  from src.appointment.domain import AppointmentSortField
  from src.core.filters import SortOrder

  execute_page = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(
    "src.appointment.repository.execute_page",
    execute_page,
  )

  await AppointmentRepository.get_internal_page(
    AsyncMock(),
    office_id=uuid.uuid4(),
    page=1,
    size=20,
    citizen_id=None,
    ticket_id=None,
    status=None,
    starts_from=None,
    starts_to=None,
    created_from=None,
    created_to=None,
    search="Ada roadwork",
    sort_by=AppointmentSortField.STARTS_AT,
    order=SortOrder.ASC,
  )

  query = str(execute_page.await_args.args[1])
  assert "users.first_name" in query
  assert "users.last_name" in query
  assert "users.email" in query
  assert "tickets.title" in query
