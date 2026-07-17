import os
import uuid

import httpx
import pytest

from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.main import app, lifespan, settings
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.service import UserService

# Import all currently active models before create_all is invoked.
import src.address.models  # noqa: F401,E402
import src.auth.models  # noqa: F401,E402
import src.office.models  # noqa: F401,E402


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


async def create_admin() -> None:
  async with AsyncSessionLocal() as db:
    admin = User(
      id=uuid.uuid4(),
      email="admin.integration@example.com",
      hashed_password=get_password_hash("password123"),
      first_name="Integration",
      last_name="Admin",
      role=Role.ADMIN,
      is_active=True,
    )
    UserRepository.add(db, admin)
    await db.flush()
    UserService.add_history_snapshot(
      db,
      admin,
      changed_by_user_id=admin.id,
      change_reason="TEST_ADMIN_CREATED",
    )
    await db.commit()


@pytest.mark.asyncio
async def test_auth_user_office_and_history_flow(monkeypatch):
  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  await create_admin()

  try:
    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        admin_login = await client.post(
          "/api/v1/auth/login",
          data={
            "username": "admin.integration@example.com",
            "password": "password123",
          },
        )
        assert admin_login.status_code == 200
        admin_tokens = admin_login.json()
        admin_headers = {
          "Authorization": f"Bearer {admin_tokens['access_token']}"
        }

        registered = await client.post(
          "/api/v1/auth/register",
          json={
            "email": "citizen.integration@example.com",
            "password": "password123",
            "first_name": "Integration",
            "last_name": "Citizen",
          },
        )
        assert registered.status_code == 201
        citizen_id = registered.json()["id"]

        citizen_login = await client.post(
          "/api/v1/auth/login",
          data={
            "username": "citizen.integration@example.com",
            "password": "password123",
          },
        )
        assert citizen_login.status_code == 200
        citizen_tokens = citizen_login.json()
        citizen_headers = {
          "Authorization": f"Bearer {citizen_tokens['access_token']}"
        }

        me = await client.get("/api/v1/users/me", headers=citizen_headers)
        assert me.status_code == 200
        assert me.json()["id"] == citizen_id

        refreshed = await client.post(
          "/api/v1/auth/refresh",
          json={"refresh_token": citizen_tokens["refresh_token"]},
        )
        assert refreshed.status_code == 200
        rotated_tokens = refreshed.json()
        assert rotated_tokens["refresh_token"] != citizen_tokens["refresh_token"]

        reused = await client.post(
          "/api/v1/auth/refresh",
          json={"refresh_token": citizen_tokens["refresh_token"]},
        )
        assert reused.status_code == 401

        office_created = await client.post(
          "/api/v1/offices",
          headers=admin_headers,
          json={
            "name": "Integration Office",
            "description": "Office used by the integration test",
          },
        )
        assert office_created.status_code == 201
        office_id = office_created.json()["id"]

        promoted = await client.patch(
          f"/api/v1/users/{citizen_id}",
          headers=admin_headers,
          json={
            "role": "OFFICER",
            "office_id": office_id,
            "change_reason": "Integration test promotion",
          },
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "OFFICER"

        user_history = await client.get(
          f"/api/v1/users/{citizen_id}/history",
          headers=admin_headers,
        )
        assert user_history.status_code == 200
        history_reasons = [
          entry["change_reason"] for entry in user_history.json()
        ]
        assert len(history_reasons) == 2
        assert set(history_reasons) == {
          "Integration test promotion",
          "USER_REGISTERED",
        }

        office_history = await client.get(
          f"/api/v1/offices/{office_id}/history",
          headers=admin_headers,
        )
        assert office_history.status_code == 200
        assert office_history.json()[0]["change_reason"] == "OFFICE_CREATED"

        blocked_delete = await client.request(
          "DELETE",
          f"/api/v1/offices/{office_id}",
          headers=admin_headers,
          json={"change_reason": "Should fail while assigned"},
        )
        assert blocked_delete.status_code == 409
        assert blocked_delete.json()["error_code"] == "OFFICE_HAS_ACTIVE_USERS"

        deactivated_user = await client.request(
          "DELETE",
          f"/api/v1/users/{citizen_id}",
          headers=admin_headers,
          json={"change_reason": "Integration test completed"},
        )
        assert deactivated_user.status_code == 204

        deactivated_office = await client.request(
          "DELETE",
          f"/api/v1/offices/{office_id}",
          headers=admin_headers,
          json={"change_reason": "Integration test completed"},
        )
        assert deactivated_office.status_code == 204

        public_offices = await client.get("/api/v1/offices?status=all")
        assert public_offices.status_code == 200
        assert all(item["id"] != office_id for item in public_offices.json()["data"])

        admin_offices = await client.get(
          "/api/v1/offices?status=all",
          headers=admin_headers,
        )
        assert admin_offices.status_code == 200
        assert any(item["id"] == office_id for item in admin_offices.json()["data"])
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
