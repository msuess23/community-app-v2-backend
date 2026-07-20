"""Destructive PostgreSQL coverage for slot booking and ticket linkage."""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import src.models  # noqa: F401
from src.appointment.event_store import AppointmentEventStore
from src.appointment.repository import AppointmentRepository
from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.main import app, lifespan
from src.office.models import Office
from src.ticket.domain import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.user.models import Role, User


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


def _headers(access_token: str) -> dict[str, str]:
  return {"Authorization": f"Bearer {access_token}"}


async def _login(client: httpx.AsyncClient, email: str) -> str:
  response = await client.post(
    "/api/v1/auth/login",
    data={"username": email, "password": "password123"},
  )
  assert response.status_code == 200
  return response.json()["access_token"]


@pytest.mark.asyncio
async def test_slot_booking_is_concurrent_and_ticket_aware(monkeypatch) -> None:
  """Only one citizen may book a slot and linked bookings remain replayable."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  office_id = uuid.uuid4()
  manager_id = uuid.uuid4()
  citizen_one_id = uuid.uuid4()
  citizen_two_id = uuid.uuid4()
  ticket_id = uuid.uuid4()
  now = datetime.now(timezone.utc)

  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          Office(
            id=office_id,
            name="Appointment Integration Office",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          User(
            id=manager_id,
            email="appointment.manager@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Appointment",
            last_name="Manager",
            role=Role.MANAGER,
            office_id=office_id,
            is_active=True,
          ),
          User(
            id=citizen_one_id,
            email="appointment.citizen.one@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Citizen",
            last_name="One",
            role=Role.CITIZEN,
            is_active=True,
          ),
          User(
            id=citizen_two_id,
            email="appointment.citizen.two@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Citizen",
            last_name="Two",
            role=Role.CITIZEN,
            is_active=True,
          ),
          Ticket(
            id=ticket_id,
            title="Road damage appointment",
            category=TicketCategory.INFRASTRUCTURE,
            creator_user_id=citizen_one_id,
            office_id=office_id,
            visibility=TicketVisibility.PRIVATE,
            public_status=TicketStatus.IN_PROGRESS,
            workflow_state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
            version=1,
            created_at=now,
            updated_at=now,
          ),
        ]
      )
      await db.commit()

    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        manager_token = await _login(client, "appointment.manager@example.com")
        citizen_one_token = await _login(
          client,
          "appointment.citizen.one@example.com",
        )
        citizen_two_token = await _login(
          client,
          "appointment.citizen.two@example.com",
        )

        first_start = now + timedelta(days=2)
        created = await client.post(
          f"/api/v1/offices/{office_id}/appointment-slots",
          headers=_headers(manager_token),
          json={
            "slots": [
              {
                "starts_at": first_start.isoformat(),
                "ends_at": (first_start + timedelta(minutes=30)).isoformat(),
              },
              {
                "starts_at": (first_start + timedelta(minutes=30)).isoformat(),
                "ends_at": (first_start + timedelta(minutes=60)).isoformat(),
              },
            ]
          },
        )
        assert created.status_code == 201
        first_slot_id, linked_slot_id = [item["id"] for item in created.json()]

        public_slots = await client.get(
          f"/api/v1/offices/{office_id}/appointment-slots"
        )
        assert public_slots.status_code == 200
        assert public_slots.json()["total"] == 2

        first_booking, second_booking = await asyncio.gather(
          client.post(
            f"/api/v1/appointment-slots/{first_slot_id}/book",
            headers=_headers(citizen_one_token),
            json={"reason": "First concurrent attempt"},
          ),
          client.post(
            f"/api/v1/appointment-slots/{first_slot_id}/book",
            headers=_headers(citizen_two_token),
            json={"reason": "Second concurrent attempt"},
          ),
        )
        assert sorted([first_booking.status_code, second_booking.status_code]) == [
          201,
          409,
        ]

        linked_booking = await client.post(
          f"/api/v1/appointment-slots/{linked_slot_id}/book",
          headers=_headers(citizen_one_token),
          json={
            "ticket_id": str(ticket_id),
            "reason": "Discuss the road damage ticket",
          },
        )
        assert linked_booking.status_code == 201
        linked_appointment = linked_booking.json()
        assert linked_appointment["ticket_id"] == str(ticket_id)
        assert linked_appointment["version"] == 1

        mine = await client.get(
          "/api/v1/appointments/mine",
          headers=_headers(citizen_one_token),
        )
        assert mine.status_code == 200
        assert any(
          item["id"] == linked_appointment["id"] for item in mine.json()["data"]
        )

        internal = await client.get(
          "/api/v1/appointments/internal",
          headers=_headers(manager_token),
          params={"ticket_id": str(ticket_id)},
        )
        assert internal.status_code == 200
        assert [item["id"] for item in internal.json()["data"]] == [
          linked_appointment["id"]
        ]

    async with AsyncSessionLocal() as db:
      appointment = await AppointmentRepository.get_by_id(
        db,
        uuid.UUID(linked_appointment["id"]),
      )
      assert appointment is not None
      rebuilt = await AppointmentEventStore.rebuild(db, appointment.id)
      assert rebuilt == AppointmentEventStore.state_from_appointment(appointment)
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_appointment_lifecycle_and_reschedule_concurrency(monkeypatch) -> None:
  """Exercise reschedule, cancel, completion, no-show and event replay via HTTP."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  office_id = uuid.uuid4()
  manager_id = uuid.uuid4()
  citizen_one_id = uuid.uuid4()
  citizen_two_id = uuid.uuid4()
  now = datetime.now(timezone.utc)

  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          Office(
            id=office_id,
            name="Appointment Lifecycle Office",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          User(
            id=manager_id,
            email="lifecycle.manager@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Lifecycle",
            last_name="Manager",
            role=Role.MANAGER,
            office_id=office_id,
            is_active=True,
          ),
          User(
            id=citizen_one_id,
            email="lifecycle.citizen.one@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Lifecycle",
            last_name="One",
            role=Role.CITIZEN,
            is_active=True,
          ),
          User(
            id=citizen_two_id,
            email="lifecycle.citizen.two@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Lifecycle",
            last_name="Two",
            role=Role.CITIZEN,
            is_active=True,
          ),
        ]
      )
      await db.commit()

    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        manager_token = await _login(client, "lifecycle.manager@example.com")
        citizen_one_token = await _login(
          client,
          "lifecycle.citizen.one@example.com",
        )
        citizen_two_token = await _login(
          client,
          "lifecycle.citizen.two@example.com",
        )
        tokens = {
          citizen_one_id: citizen_one_token,
          citizen_two_id: citizen_two_token,
        }

        base_start = now + timedelta(days=5)
        created = await client.post(
          f"/api/v1/offices/{office_id}/appointment-slots",
          headers=_headers(manager_token),
          json={
            "slots": [
              {
                "starts_at": (base_start + timedelta(days=index)).isoformat(),
                "ends_at": (
                  base_start + timedelta(days=index, minutes=30)
                ).isoformat(),
              }
              for index in range(5)
            ]
          },
        )
        assert created.status_code == 201
        source_one, source_two, shared_target, completion_slot, no_show_slot = [
          item["id"] for item in created.json()
        ]

        booking_one = await client.post(
          f"/api/v1/appointment-slots/{source_one}/book",
          headers=_headers(citizen_one_token),
          json={"reason": "First source appointment"},
        )
        booking_two = await client.post(
          f"/api/v1/appointment-slots/{source_two}/book",
          headers=_headers(citizen_two_token),
          json={"reason": "Second source appointment"},
        )
        assert booking_one.status_code == booking_two.status_code == 201

        appointment_one = booking_one.json()
        appointment_two = booking_two.json()
        reschedule_one, reschedule_two = await asyncio.gather(
          client.post(
            f"/api/v1/appointments/{appointment_one['id']}/reschedule",
            headers=_headers(citizen_one_token),
            json={
              "target_slot_id": shared_target,
              "reason": "Move to the shared target",
            },
          ),
          client.post(
            f"/api/v1/appointments/{appointment_two['id']}/reschedule",
            headers=_headers(citizen_two_token),
            json={
              "target_slot_id": shared_target,
              "reason": "Move to the shared target",
            },
          ),
        )
        assert sorted([reschedule_one.status_code, reschedule_two.status_code]) == [
          200,
          409,
        ]

        successful = (
          reschedule_one if reschedule_one.status_code == 200 else reschedule_two
        ).json()
        winner_id = uuid.UUID(successful["citizen_id"])
        cancelled = await client.post(
          f"/api/v1/appointments/{successful['id']}/cancel",
          headers=_headers(tokens[winner_id]),
          json={"reason": "The appointment is no longer needed"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["current_slot_id"] is None
        assert cancelled.json()["version"] == 3

        losing_appointment = (
          appointment_two if winner_id == citizen_one_id else appointment_one
        )
        losing_token = (
          citizen_two_token if winner_id == citizen_one_id else citizen_one_token
        )
        retry = await client.post(
          f"/api/v1/appointments/{losing_appointment['id']}/reschedule",
          headers=_headers(losing_token),
          json={
            "target_slot_id": shared_target,
            "reason": "Use the slot released by cancellation",
          },
        )
        assert retry.status_code == 200
        assert retry.json()["current_slot_id"] == shared_target
        assert retry.json()["version"] == 2

        completion_booking = await client.post(
          f"/api/v1/appointment-slots/{completion_slot}/book",
          headers=_headers(citizen_one_token),
          json={"reason": "Appointment to complete"},
        )
        no_show_booking = await client.post(
          f"/api/v1/appointment-slots/{no_show_slot}/book",
          headers=_headers(citizen_two_token),
          json={"reason": "Appointment to mark as no-show"},
        )
        assert completion_booking.status_code == no_show_booking.status_code == 201

        frozen_now = base_start + timedelta(days=5, minutes=1)

        class FrozenDateTime(datetime):
          @classmethod
          def now(cls, tz=None):
            return frozen_now if tz is None else frozen_now.astimezone(tz)

        monkeypatch.setattr(
          "src.appointment.lifecycle_service.datetime",
          FrozenDateTime,
        )

        completed = await client.post(
          f"/api/v1/appointments/{completion_booking.json()['id']}/complete",
          headers=_headers(manager_token),
          json={"comment": "Citizen request processed"},
        )
        no_show = await client.post(
          f"/api/v1/appointments/{no_show_booking.json()['id']}/no-show",
          headers=_headers(manager_token),
          json={"comment": "Citizen did not attend"},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "COMPLETED"
        assert completed.json()["version"] == 2
        assert no_show.status_code == 200
        assert no_show.json()["status"] == "NO_SHOW"

        citizen_events = await client.get(
          f"/api/v1/appointments/{completion_booking.json()['id']}/events",
          headers=_headers(citizen_one_token),
        )
        manager_events = await client.get(
          f"/api/v1/appointments/{completion_booking.json()['id']}/events",
          headers=_headers(manager_token),
        )
        assert citizen_events.status_code == manager_events.status_code == 200
        assert citizen_events.json()["total"] == 2
        assert citizen_events.json()["data"][1]["actor_user_id"] is None
        assert manager_events.json()["data"][1]["actor_user_id"] == str(manager_id)

    async with AsyncSessionLocal() as db:
      completed_id = uuid.UUID(completion_booking.json()["id"])
      appointment = await AppointmentRepository.get_by_id(db, completed_id)
      assert appointment is not None
      rebuilt = await AppointmentEventStore.rebuild(db, completed_id)
      assert rebuilt == AppointmentEventStore.state_from_appointment(appointment)
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_appointment_document_versions_are_audited_and_access_controlled(
  monkeypatch,
  tmp_path,
) -> None:
  """Retain PDF revisions while exposing only the current citizen-visible file."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
  monkeypatch.setattr(settings, "APPOINTMENT_DOCUMENT_ROOT", str(tmp_path))

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  office_id = uuid.uuid4()
  manager_id = uuid.uuid4()
  citizen_id = uuid.uuid4()
  now = datetime.now(timezone.utc)
  pdf_v1 = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
  pdf_v2 = b"%PDF-1.4\n2 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          Office(
            id=office_id,
            name="Appointment Document Office",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          User(
            id=manager_id,
            email="document.manager@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Document",
            last_name="Manager",
            role=Role.MANAGER,
            office_id=office_id,
            is_active=True,
          ),
          User(
            id=citizen_id,
            email="document.citizen@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Document",
            last_name="Citizen",
            role=Role.CITIZEN,
            is_active=True,
          ),
        ]
      )
      await db.commit()

    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        manager_token = await _login(client, "document.manager@example.com")
        citizen_token = await _login(client, "document.citizen@example.com")

        start = now + timedelta(days=2)
        slots = await client.post(
          f"/api/v1/offices/{office_id}/appointment-slots",
          headers=_headers(manager_token),
          json={
            "slots": [
              {
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(minutes=30)).isoformat(),
              }
            ]
          },
        )
        assert slots.status_code == 201
        booking = await client.post(
          f"/api/v1/appointment-slots/{slots.json()[0]['id']}/book",
          headers=_headers(citizen_token),
          json={"reason": "Appointment with versioned documents"},
        )
        assert booking.status_code == 201
        appointment_id = booking.json()["id"]

        first = await client.post(
          f"/api/v1/appointments/{appointment_id}/documents",
          headers=_headers(manager_token),
          files={"file": ("notice-v1.pdf", pdf_v1, "application/pdf")},
          data={
            "document_type": "NOTICE",
            "visible_to_citizen": "true",
          },
        )
        assert first.status_code == 201
        first_document = first.json()
        assert first_document["version_number"] == 1

        replacement = await client.post(
          f"/api/v1/appointments/{appointment_id}/documents",
          headers=_headers(manager_token),
          files={"file": ("notice-v2.pdf", pdf_v2, "application/pdf")},
          data={
            "document_type": "NOTICE",
            "visible_to_citizen": "true",
            "replace_document_group_id": first_document["document_group_id"],
          },
        )
        assert replacement.status_code == 201
        second_document = replacement.json()
        assert second_document["version_number"] == 2
        assert second_document["replaced_version_id"] == first_document["id"]

        citizen_documents = await client.get(
          f"/api/v1/appointments/{appointment_id}/documents",
          headers=_headers(citizen_token),
        )
        assert citizen_documents.status_code == 200
        assert [item["id"] for item in citizen_documents.json()] == [
          second_document["id"]
        ]

        old_citizen_download = await client.get(
          f"/api/v1/appointments/{appointment_id}/documents/"
          f"{first_document['id']}/content",
          headers=_headers(citizen_token),
        )
        current_citizen_download = await client.get(
          f"/api/v1/appointments/{appointment_id}/documents/"
          f"{second_document['id']}/content",
          headers=_headers(citizen_token),
        )
        assert old_citizen_download.status_code == 404
        assert current_citizen_download.status_code == 200
        assert current_citizen_download.content == pdf_v2

        versions = await client.get(
          f"/api/v1/appointments/{appointment_id}/documents/"
          f"{first_document['document_group_id']}/versions",
          headers=_headers(manager_token),
        )
        assert versions.status_code == 200
        assert [item["version_number"] for item in versions.json()] == [2, 1]

        old_staff_download = await client.get(
          f"/api/v1/appointments/{appointment_id}/documents/"
          f"{first_document['id']}/content",
          headers=_headers(manager_token),
        )
        assert old_staff_download.status_code == 200
        assert old_staff_download.content == pdf_v1

        events = await client.get(
          f"/api/v1/appointments/{appointment_id}/events",
          headers=_headers(manager_token),
        )
        assert events.status_code == 200
        assert [item["event_type"] for item in events.json()["data"]] == [
          "APPOINTMENT_BOOKED",
          "DOCUMENT_VERSION_ADDED",
          "DOCUMENT_VERSION_ADDED",
        ]

    async with AsyncSessionLocal() as db:
      appointment = await AppointmentRepository.get_by_id(
        db,
        uuid.UUID(appointment_id),
      )
      assert appointment is not None
      assert appointment.version == 3
      rebuilt = await AppointmentEventStore.rebuild(db, appointment.id)
      assert rebuilt == AppointmentEventStore.state_from_appointment(appointment)
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
