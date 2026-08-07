from dataclasses import dataclass
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.media.cover import CoverChange
from src.media.cover_persistence import apply_cover_change_safely


@dataclass
class _Image:
  id: UUID
  is_active: bool = True
  is_cover: bool = False


@pytest.mark.asyncio
async def test_cover_persistence_releases_previous_cover_before_selecting_next():
  previous = _Image(UUID(int=2), is_cover=True)
  selected = _Image(UUID(int=1))
  states: list[tuple[bool, bool]] = []

  async def record_flush():
    states.append((previous.is_cover, selected.is_cover))

  db = AsyncMock()
  db.flush = AsyncMock(side_effect=record_flush)

  result = await apply_cover_change_safely(
    db,
    [previous, selected],
    CoverChange(previous_cover_id=previous.id, new_cover_id=selected.id),
  )

  assert states == [(False, False)]
  assert previous.is_cover is False
  assert selected.is_cover is True
  assert result is selected
