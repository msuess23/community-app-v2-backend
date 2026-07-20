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
