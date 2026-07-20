"""Destructive PostgreSQL coverage for current Info images and hard deletion."""

import io
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from PIL import Image
from sqlalchemy import func, select

import src.models  # noqa: F401
from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.info.models import InfoImage
from src.main import app, lifespan
from src.office.models import Office
from src.user.models import Role, User


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


def _headers(access_token: str) -> dict[str, str]:
  return {"Authorization": f"Bearer {access_token}"}


def _png_bytes(width: int, height: int) -> bytes:
  buffer = io.BytesIO()
  Image.new("RGB", (width, height)).save(buffer, format="PNG")
  return buffer.getvalue()


async def _login(client: httpx.AsyncClient, email: str) -> str:
  response = await client.post(
    "/api/v1/auth/login",
    data={"username": email, "password": "password123"},
  )
  assert response.status_code == 200
  return response.json()["access_token"]


@pytest.mark.asyncio
async def test_info_images_cover_content_and_physical_deletion(
  monkeypatch,
  tmp_path,
) -> None:
  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  media_root = tmp_path / "info-media"
  monkeypatch.setattr(settings, "INFO_MEDIA_ROOT", str(media_root))
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
            name="Info Image Office",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          User(
            id=manager_id,
            email="info.images.manager@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Image",
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
        token = await _login(client, "info.images.manager@example.com")
        created = await client.post(
          "/api/v1/infos",
          headers=_headers(token),
          json={
            "title": "Public event",
            "category": "EVENT",
            "office_id": str(office_id),
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
          },
        )
        assert created.status_code == 201
        info_id = created.json()["id"]

        first = await client.post(
          f"/api/v1/infos/{info_id}/images",
          headers=_headers(token),
          files={"file": ("first.png", _png_bytes(20, 10), "image/png")},
        )
        second = await client.post(
          f"/api/v1/infos/{info_id}/images",
          headers=_headers(token),
          files={"file": ("second.png", _png_bytes(30, 15), "image/png")},
        )
        assert first.status_code == second.status_code == 201
        assert first.json()["is_cover"] is True
        assert second.json()["is_cover"] is False
        assert len(list(media_root.rglob("*.png"))) == 2

        detail = await client.get(f"/api/v1/infos/{info_id}")
        assert detail.status_code == 200
        assert detail.json()["image_url"] == first.json()["url"]

        selected = await client.put(
          f"/api/v1/infos/{info_id}/images/{second.json()['id']}/cover",
          headers=_headers(token),
        )
        assert selected.status_code == 200
        assert selected.json()["is_cover"] is True
        assert (await client.get(f"/api/v1/infos/{info_id}")).json()[
          "image_url"
        ] == second.json()["url"]

        content = await client.get(second.json()["url"])
        assert content.status_code == 200
        assert content.headers["content-type"].startswith("image/png")

        deleted_cover = await client.delete(
          f"/api/v1/infos/{info_id}/images/{second.json()['id']}",
          headers=_headers(token),
        )
        assert deleted_cover.status_code == 204
        assert len(list(media_root.rglob("*.png"))) == 1
        remaining = await client.get(f"/api/v1/infos/{info_id}/images")
        assert remaining.status_code == 200
        assert len(remaining.json()) == 1
        assert remaining.json()[0]["id"] == first.json()["id"]
        assert remaining.json()[0]["is_cover"] is True

        deleted_info = await client.delete(
          f"/api/v1/infos/{info_id}",
          headers=_headers(token),
        )
        assert deleted_info.status_code == 204
        assert list(media_root.rglob("*.png")) == []
        assert (await client.get(first.json()["url"])).status_code == 404

    async with AsyncSessionLocal() as db:
      image_count = int(
        (
          await db.execute(select(func.count()).select_from(InfoImage))
        ).scalar_one()
      )
      assert image_count == 0
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
