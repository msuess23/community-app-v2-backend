from datetime import datetime, timezone

import pytest

from src.core.exceptions import DomainValidationException
from src.core.query_params import (
  get_created_date_range,
  get_history_date_range,
  get_page_params,
  get_search_params,
)


def test_common_page_and_search_params_are_normalized() -> None:
  page = get_page_params(page=3, size=25)
  search = get_search_params(q="  road damage  ")

  assert (page.page, page.size) == (3, 25)
  assert search.q == "road damage"
  assert get_search_params(q="   ").q is None


def test_date_range_rejects_reversed_bounds() -> None:
  start = datetime(2026, 7, 2, tzinfo=timezone.utc)
  end = datetime(2026, 7, 1, tzinfo=timezone.utc)

  with pytest.raises(DomainValidationException) as exc_info:
    get_created_date_range(created_from=start, created_to=end)

  assert exc_info.value.error_code == "INVALID_DATE_RANGE"


def test_history_date_range_accepts_open_bounds() -> None:
  start = datetime(2026, 7, 1, tzinfo=timezone.utc)
  date_range = get_history_date_range(start_date=start, end_date=None)

  assert date_range.start == start
  assert date_range.end is None


def test_date_range_requires_timezone_aware_values() -> None:
  with pytest.raises(DomainValidationException) as exc_info:
    get_history_date_range(
      start_date=datetime(2026, 7, 1),
      end_date=None,
    )

  assert exc_info.value.error_code == "DATE_TIMEZONE_REQUIRED"
