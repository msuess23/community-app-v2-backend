"""Reusable FastAPI query-parameter groups and range validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Query

from src.core.exceptions import DomainValidationException


@dataclass(frozen=True)
class PageParams:
  """Validated page-based pagination parameters."""

  page: int
  size: int


@dataclass(frozen=True)
class SearchParams:
  """Normalized optional free-text search input."""

  q: str | None


@dataclass(frozen=True)
class DateRangeParams:
  """Optional inclusive datetime range used by list and history endpoints."""

  start: datetime | None
  end: datetime | None


def get_page_params(
  page: int = Query(1, ge=1),
  size: int = Query(20, ge=1, le=100),
) -> PageParams:
  """Return common page parameters for list endpoints."""

  return PageParams(page=page, size=size)


def get_search_params(
  q: str | None = Query(None, max_length=200),
) -> SearchParams:
  """Return a trimmed search term or None when no search is requested."""

  normalized = q.strip() if q is not None else None
  return SearchParams(q=normalized or None)


def _validated_range(
  start: datetime | None,
  end: datetime | None,
) -> DateRangeParams:
  for value in (start, end):
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
      raise DomainValidationException(
        "Date range values must include a timezone.",
        error_code="DATE_TIMEZONE_REQUIRED",
      )

  if start is not None and end is not None and start > end:
    raise DomainValidationException(
      "The start of a date range must not be after its end.",
      error_code="INVALID_DATE_RANGE",
    )
  return DateRangeParams(start=start, end=end)


def get_history_date_range(
  start_date: datetime | None = Query(None),
  end_date: datetime | None = Query(None),
) -> DateRangeParams:
  """Validate the conventional start_date/end_date history parameters."""

  return _validated_range(start_date, end_date)


def get_created_date_range(
  created_from: datetime | None = Query(None),
  created_to: datetime | None = Query(None),
) -> DateRangeParams:
  """Validate the created_from/created_to ticket list parameters."""

  return _validated_range(created_from, created_to)


def get_starts_date_range(
  starts_from: datetime | None = Query(None),
  starts_to: datetime | None = Query(None),
) -> DateRangeParams:
  """Validate the starts_from/starts_to appointment parameters."""

  return _validated_range(starts_from, starts_to)


def get_updated_date_range(
  updated_from: datetime | None = Query(None),
  updated_to: datetime | None = Query(None),
) -> DateRangeParams:
  """Validate the updated_from/updated_to internal-search parameters."""

  return _validated_range(updated_from, updated_to)
