"""Destructive PostgreSQL coverage for final pre-appointment backend behavior."""

import asyncio
import os
import uuid

import httpx
import pytest

from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.main import app, lifespan
from src.office.models import Office
from src.user.models import Role, User

# Register every active model before metadata.create_all is called.
import src.models  # noqa: F401,E402


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


async def _login(client: httpx.AsyncClient, email: str) -> dict:
  response = await client.post(
    "/api/v1/auth/login",
    data={"username": email, "password": "password123"},
  )
  assert response.status_code == 200
  return response.json()


def _headers(tokens: dict) -> dict[str, str]:
  return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_reassignment_redispatch_archive_refresh_rotation_and_logout_all(
  monkeypatch,
) -> None:
  """Exercise the final ticket and authentication additions through HTTP."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  office_a_id = uuid.uuid4()
  office_b_id = uuid.uuid4()
  users = {
    "citizen": User(
      id=uuid.uuid4(),
      email="final.citizen@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Final",
      last_name="Citizen",
      role=Role.CITIZEN,
      is_active=True,
    ),
    "dispatcher": User(
      id=uuid.uuid4(),
      email="final.dispatcher@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Final",
      last_name="Dispatcher",
      role=Role.DISPATCHER,
      is_active=True,
    ),
    "manager_a": User(
      id=uuid.uuid4(),
      email="final.manager.a@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Manager",
      last_name="Alpha",
      role=Role.MANAGER,
      office_id=office_a_id,
      is_active=True,
    ),
    "officer_a1": User(
      id=uuid.uuid4(),
      email="final.officer.a1@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Officer",
      last_name="Alpha One",
      role=Role.OFFICER,
      office_id=office_a_id,
      is_active=True,
    ),
    "officer_a2": User(
      id=uuid.uuid4(),
      email="final.officer.a2@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Officer",
      last_name="Alpha Two",
      role=Role.OFFICER,
      office_id=office_a_id,
      is_active=True,
    ),
    "manager_b": User(
      id=uuid.uuid4(),
      email="final.manager.b@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Manager",
      last_name="Beta",
      role=Role.MANAGER,
      office_id=office_b_id,
      is_active=True,
    ),
    "officer_b": User(
      id=uuid.uuid4(),
      email="final.officer.b@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Officer",
      last_name="Beta",
      role=Role.OFFICER,
      office_id=office_b_id,
      is_active=True,
    ),
  }

  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          Office(
            id=office_a_id,
            name="Office Alpha",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          Office(
            id=office_b_id,
            name="Office Beta",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          *users.values(),
        ]
      )
      await db.commit()

    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        tokens = {
          name: await _login(client, user.email)
          for name, user in users.items()
        }

        # A refresh token is consumed atomically; only one concurrent rotation wins.
        refresh_token = tokens["citizen"]["refresh_token"]
        first_refresh, second_refresh = await asyncio.gather(
          client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
          ),
          client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
          ),
        )
        assert sorted([first_refresh.status_code, second_refresh.status_code]) == [200, 401]

        created = await client.post(
          "/api/v1/tickets",
          headers=_headers(tokens["citizen"]),
          json={
            "title": "Road damage requiring another authority",
            "category": "INFRASTRUCTURE",
          },
        )
        assert created.status_code == 201
        ticket_id = created.json()["id"]

        dispatched_a = await client.post(
          f"/api/v1/tickets/{ticket_id}/dispatch",
          headers=_headers(tokens["dispatcher"]),
          json={"office_id": str(office_a_id)},
        )
        assert dispatched_a.status_code == 200

        assigned_a1 = await client.post(
          f"/api/v1/tickets/{ticket_id}/primary-officer",
          headers=_headers(tokens["manager_a"]),
          json={"primary_officer_id": str(users["officer_a1"].id)},
        )
        assert assigned_a1.status_code == 200

        reassigned_a2 = await client.post(
          f"/api/v1/tickets/{ticket_id}/primary-officer",
          headers=_headers(tokens["manager_a"]),
          json={
            "primary_officer_id": str(users["officer_a2"].id),
            "comment": "Long-term substitution",
          },
        )
        assert reassigned_a2.status_code == 200
        assert reassigned_a2.json()["primary_officer_id"] == str(
          users["officer_a2"].id
        )
        assert reassigned_a2.json()["current_assignee_id"] == str(
          users["officer_a2"].id
        )

        returned = await client.post(
          f"/api/v1/tickets/{ticket_id}/workflow",
          headers=_headers(tokens["officer_a2"]),
          json={
            "action": "RETURN_TO_DISPATCH",
            "reason": "Office Beta is responsible",
          },
        )
        assert returned.status_code == 200
        assert returned.json()["office_id"] is None
        assert returned.json()["workflow_state"] == "NEW"

        dispatched_b = await client.post(
          f"/api/v1/tickets/{ticket_id}/dispatch",
          headers=_headers(tokens["dispatcher"]),
          json={"office_id": str(office_b_id)},
        )
        assert dispatched_b.status_code == 200

        assigned_b = await client.post(
          f"/api/v1/tickets/{ticket_id}/primary-officer",
          headers=_headers(tokens["manager_b"]),
          json={"primary_officer_id": str(users["officer_b"].id)},
        )
        assert assigned_b.status_code == 200

        completed = await client.post(
          f"/api/v1/tickets/{ticket_id}/workflow",
          headers=_headers(tokens["officer_b"]),
          json={
            "action": "COMPLETE",
            "outcome": "RESOLVED",
            "message": "Road damage repaired",
          },
        )
        assert completed.status_code == 200
        assert completed.json()["workflow_state"] == "COMPLETED"

        archive = await client.get(
          "/api/v1/tickets/internal",
          headers=_headers(tokens["manager_b"]),
          params={
            "lifecycle": "completed",
            "office_id": str(office_b_id),
            "primary_officer_id": str(users["officer_b"].id),
            "q": "road damage",
          },
        )
        assert archive.status_code == 200
        assert archive.json()["total"] == 1
        assert archive.json()["data"][0]["id"] == ticket_id

        old_office_archive = await client.get(
          "/api/v1/tickets/internal",
          headers=_headers(tokens["manager_a"]),
          params={"lifecycle": "all", "q": "road damage"},
        )
        assert old_office_archive.status_code == 200
        assert old_office_archive.json()["total"] == 0

        events = await client.get(
          f"/api/v1/tickets/{ticket_id}/events",
          headers=_headers(tokens["manager_b"]),
        )
        assert events.status_code == 200
        event_types = [event["event_type"] for event in events.json()["data"]]
        assert "PRIMARY_OFFICER_REASSIGNED" in event_types
        assert "TICKET_RETURNED_TO_DISPATCH" in event_types

        logout_all = await client.post(
          "/api/v1/auth/logout-all",
          headers=_headers(tokens["manager_b"]),
        )
        assert logout_all.status_code == 200
        invalidated = await client.post(
          "/api/v1/auth/refresh",
          json={"refresh_token": tokens["manager_b"]["refresh_token"]},
        )
        assert invalidated.status_code == 401
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
