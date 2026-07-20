"""Destructive PostgreSQL coverage for final correctness hardening."""

import asyncio
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select

import src.models  # noqa: F401
import src.ticket.services.images as ticket_image_module
from src.auth.models import PasswordReset
from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.main import app, lifespan
from src.user.models import Role, User


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


def _png_bytes() -> bytes:
  buffer = io.BytesIO()
  Image.new("RGB", (20, 10)).save(buffer, format="PNG")
  return buffer.getvalue()


async def _reset_database() -> None:
  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
  response = await client.post(
    "/api/v1/auth/login",
    data={"username": email, "password": password},
  )
  assert response.status_code == 200
  return response.json()["access_token"]


@pytest.mark.asyncio
async def test_ticket_cover_switch_is_safe_for_unfavourable_uuid_order(
  monkeypatch,
  tmp_path,
) -> None:
  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "TICKET_MEDIA_ROOT", str(tmp_path / "ticket-media"))
  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
  await _reset_database()

  email = "cover.hardening@example.com"
  try:
    async with AsyncSessionLocal() as db:
      db.add(
        User(
          id=uuid.uuid4(),
          email=email,
          hashed_password=get_password_hash("password123"),
          first_name="Cover",
          last_name="Hardening",
          role=Role.CITIZEN,
          is_active=True,
        )
      )
      await db.commit()

    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        token = await _login(client, email, "password123")
        headers = {"Authorization": f"Bearer {token}"}
        created = await client.post(
          "/api/v1/tickets",
          headers=headers,
          json={
            "title": "Cover ordering",
            "category": "INFRASTRUCTURE",
          },
        )
        assert created.status_code == 201
        ticket_id = created.json()["id"]

        image_ids = iter([uuid.UUID(int=2), uuid.UUID(int=1)])
        monkeypatch.setattr(
          ticket_image_module,
          "uuid",
          SimpleNamespace(uuid4=lambda: next(image_ids)),
        )
        first = await client.post(
          f"/api/v1/tickets/{ticket_id}/images",
          headers=headers,
          files={"file": ("first.png", _png_bytes(), "image/png")},
        )
        second = await client.post(
          f"/api/v1/tickets/{ticket_id}/images",
          headers=headers,
          files={"file": ("second.png", _png_bytes(), "image/png")},
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == str(uuid.UUID(int=2))
        assert second.json()["id"] == str(uuid.UUID(int=1))

        content = await client.get(second.json()["url"])
        assert content.headers["content-disposition"].startswith("inline;")

        selected = await client.put(
          f"/api/v1/tickets/{ticket_id}/images/{second.json()['id']}/cover",
          headers=headers,
        )
        assert selected.status_code == 200
        assert selected.json()["is_cover"] is True

        removed = await client.delete(
          f"/api/v1/tickets/{ticket_id}/images/{second.json()['id']}",
          headers=headers,
        )
        assert removed.status_code == 204
        remaining = await client.get(f"/api/v1/tickets/{ticket_id}/images")
        assert remaining.status_code == 200
        assert remaining.json()[0]["id"] == first.json()["id"]
        assert remaining.json()[0]["is_cover"] is True
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_password_reset_otp_can_only_be_consumed_once_concurrently(
  monkeypatch,
) -> None:
  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
  await _reset_database()

  email = "otp.hardening@example.com"
  otp = "123456"
  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=get_password_hash("password123"),
            first_name="OTP",
            last_name="Hardening",
            role=Role.CITIZEN,
            is_active=True,
          ),
          PasswordReset(
            id=uuid.uuid4(),
            email=email,
            otp_hash=get_password_hash(otp),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
          ),
        ]
      )
      await db.commit()

    payload = {
      "email": email,
      "otp": otp,
      "new_password": "new-password-123",
    }
    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        first, second = await asyncio.gather(
          client.post("/api/v1/auth/reset-password", json=payload),
          client.post("/api/v1/auth/reset-password", json=payload),
        )
        assert sorted([first.status_code, second.status_code]) == [200, 422]
        await _login(client, email, "new-password-123")

    async with AsyncSessionLocal() as db:
      reset_count = int(
        (
          await db.execute(select(func.count()).select_from(PasswordReset))
        ).scalar_one()
      )
      assert reset_count == 0
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
