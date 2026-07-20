from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.info.router import get_info_image_content
from src.ticket.router.images import get_ticket_image_content


@pytest.mark.asyncio
async def test_info_image_content_is_delivered_inline(monkeypatch, tmp_path):
  path = tmp_path / "info.png"
  path.write_bytes(b"image")
  image = SimpleNamespace(mime_type="image/png", original_filename="info.png")
  monkeypatch.setattr(
    "src.info.router.InfoImageService.get_content",
    AsyncMock(return_value=(path, image)),
  )

  response = await get_info_image_content(uuid4(), uuid4(), AsyncMock())

  assert response.headers["content-disposition"].startswith("inline;")


@pytest.mark.asyncio
async def test_ticket_image_content_is_delivered_inline(monkeypatch, tmp_path):
  path = tmp_path / "ticket.png"
  path.write_bytes(b"image")
  image = SimpleNamespace(mime_type="image/png", original_filename="ticket.png")
  monkeypatch.setattr(
    "src.ticket.router.images.TicketImageService.get_content",
    AsyncMock(return_value=(path, image)),
  )

  response = await get_ticket_image_content(
    uuid4(),
    uuid4(),
    AsyncMock(),
    None,
  )

  assert response.headers["content-disposition"].startswith("inline;")
