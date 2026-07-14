from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.core.exceptions import BadRequestException
from src.core.filters import apply_search_filter, get_bbox_filter
from src.core.pagination import Page, PaginationParams
from src.user.models import User


def test_bounding_box_validates_ranges_and_order() -> None:
  bbox = get_bbox_filter("11.0,49.0,12.0,50.0")

  assert bbox is not None
  assert bbox.min_lon == 11.0
  assert bbox.max_lat == 50.0


def test_bounding_box_rejects_reversed_coordinates() -> None:
  try:
    get_bbox_filter("12.0,49.0,11.0,50.0")
  except BadRequestException as exc:
    assert exc.error_code == "INVALID_BOUNDING_BOX"
  else:
    raise AssertionError("reversed bounding box must be rejected")


def test_search_treats_sql_wildcards_as_literal_characters() -> None:
  query = apply_search_filter(select(User), "100%_\\", User.email)
  compiled = query.compile(dialect=postgresql.dialect())

  assert "ESCAPE '\\\\'" in str(compiled)
  assert compiled.params["email_1"] == "%100\\%\\_\\\\%"


def test_page_calculates_metadata() -> None:
  page = Page[int].create(
    data=[21, 22],
    total=42,
    pagination=PaginationParams(page=3, size=10),
  )

  assert page.page == 3
  assert page.size == 10
  assert page.pages == 5
  assert page.total == 42
