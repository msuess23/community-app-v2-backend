import pytest
from fastapi import HTTPException

from src.core.filters import escape_like_pattern, get_bbox_filter


def test_search_wildcards_are_escaped():
  assert escape_like_pattern("50%_off\\today") == r"50\%\_off\\today"


@pytest.mark.asyncio
@pytest.mark.parametrize(
  "bbox",
  [
    "-181,0,1,1",
    "0,-91,1,1",
    "10,0,5,1",
    "0,10,1,5",
    "0,0,1",
  ],
)
async def test_invalid_bbox_is_rejected(bbox: str):
  with pytest.raises(HTTPException):
    await get_bbox_filter(bbox)


@pytest.mark.asyncio
async def test_valid_bbox_is_parsed():
  assert await get_bbox_filter("10,20,30,40") == (10.0, 20.0, 30.0, 40.0)
