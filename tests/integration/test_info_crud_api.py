"""Destructive PostgreSQL coverage for classical Info CRUD and hard deletion."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select

import src.models  # noqa: F401
from src.address.models import Address
from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.info.models import Info, InfoStatusEntry
from src.main import app, lifespan
from src.office.models import Office
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
async def test_info_create_update_status_and_physical_delete(monkeypatch) -> None:
  """The same Info row is updated and DELETE removes all owned database rows."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  office_id = uuid.uuid4()
  manager_id = uuid.uuid4()
  starts_at = datetime.now(timezone.utc) + timedelta(days=1)

  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          Office(
            id=office_id,
            name="Info Integration Office",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          User(
            id=manager_id,
            email="info.manager@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Info",
            last_name="Manager",
            role=Role.MANAGER,
            office_id=office_id,
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
        token = await _login(client, "info.manager@example.com")
        created = await client.post(
          "/api/v1/infos",
          headers=_headers(token),
          json={
            "title": "Road construction",
            "description": "Temporary traffic restrictions",
            "category": "CONSTRUCTION",
            "office_id": str(office_id),
            "address": {
              "street": "Main Street",
              "house_number": "10",
              "zip_code": "95028",
              "city": "Hof",
              "latitude": 50.31,
              "longitude": 11.91,
            },
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(days=2)).isoformat(),
          },
        )
        assert created.status_code == 201
        info = created.json()
        info_id = info["id"]
        address_id = info["address"]["id"]
        assert info["current_status"]["status"] == "SCHEDULED"
        assert info["image_url"] is None

        listed = await client.get(
          "/api/v1/infos",
          params={
            "q": "construction",
            "office_id": str(office_id),
            "category": "CONSTRUCTION",
            "bbox": "11.8,50.2,12.0,50.4",
          },
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["data"][0]["id"] == info_id

        updated = await client.put(
          f"/api/v1/infos/{info_id}",
          headers=_headers(token),
          json={
            "title": "Updated road construction",
            "description": None,
          },
        )
        assert updated.status_code == 200
        assert updated.json()["id"] == info_id
        assert updated.json()["description"] is None

        status_update = await client.put(
          f"/api/v1/infos/{info_id}/status",
          headers=_headers(token),
          json={"status": "ACTIVE", "message": "Construction started"},
        )
        assert status_update.status_code == 200
        assert status_update.json()["status"] == "ACTIVE"

        status_history = await client.get(f"/api/v1/infos/{info_id}/status")
        assert status_history.status_code == 200
        assert [item["status"] for item in status_history.json()] == [
          "ACTIVE",
          "SCHEDULED",
        ]

        deleted = await client.delete(
          f"/api/v1/infos/{info_id}",
          headers=_headers(token),
        )
        assert deleted.status_code == 204
        assert (await client.get(f"/api/v1/infos/{info_id}")).status_code == 404

    async with AsyncSessionLocal() as db:
      assert await db.get(Info, uuid.UUID(info_id)) is None
      assert await db.get(Address, uuid.UUID(address_id)) is None
      status_count = int(
        (
          await db.execute(
            select(func.count()).select_from(InfoStatusEntry).where(
              InfoStatusEntry.info_id == uuid.UUID(info_id)
            )
          )
        ).scalar_one()
      )
      assert status_count == 0
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
