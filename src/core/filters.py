from enum import Enum
from typing import Optional

from fastapi import Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_
from sqlalchemy.sql import Select

from src.core.exceptions import BadRequestException
from src.core.normalization import normalize_optional_text


class BoundingBox(BaseModel):
  """Validated WGS84 bounding box."""

  min_lon: float = Field(ge=-180.0, le=180.0)
  min_lat: float = Field(ge=-90.0, le=90.0)
  max_lon: float = Field(ge=-180.0, le=180.0)
  max_lat: float = Field(ge=-90.0, le=90.0)

  @model_validator(mode="after")
  def validate_order(self) -> "BoundingBox":
    if self.min_lon > self.max_lon:
      raise ValueError("min_lon must be less than or equal to max_lon")
    if self.min_lat > self.max_lat:
      raise ValueError("min_lat must be less than or equal to max_lat")
    return self


def get_bbox_filter(
  bbox: Optional[str] = Query(
    None,
    description="Bounding Box: minLon,minLat,maxLon,maxLat",
  ),
) -> Optional[BoundingBox]:
  """Parse and validate a comma-separated WGS84 bounding box."""
  if bbox is None:
    return None

  try:
    parts = [part.strip() for part in bbox.split(",")]
    if len(parts) != 4:
      raise ValueError("bbox must contain exactly four coordinates")
    return BoundingBox(
      min_lon=float(parts[0]),
      min_lat=float(parts[1]),
      max_lon=float(parts[2]),
      max_lat=float(parts[3]),
    )
  except (TypeError, ValueError) as exc:
    raise BadRequestException(
      "Invalid bounding box. Expected minLon,minLat,maxLon,maxLat in WGS84 ranges.",
      error_code="INVALID_BOUNDING_BOX",
      details={"field": "bbox"},
    ) from exc


def apply_bbox_filter(
  query: Select,
  address_model,
  bbox: Optional[BoundingBox],
) -> Select:
  """Apply a validated bounding-box filter to a joined address model."""
  if bbox is None:
    return query

  return query.where(
    address_model.latitude >= bbox.min_lat,
    address_model.latitude <= bbox.max_lat,
    address_model.longitude >= bbox.min_lon,
    address_model.longitude <= bbox.max_lon,
  )


def _escape_like(term: str) -> str:
  return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_search_filter(query: Select, search_term: Optional[str], *columns) -> Select:
  """Apply normalized literal substring search across the supplied columns."""
  normalized = normalize_optional_text(search_term)
  if normalized is None:
    return query

  pattern = f"%{_escape_like(normalized)}%"
  return query.where(
    or_(*[column.ilike(pattern, escape="\\") for column in columns])
  )


class LifecycleStatusFilter(str, Enum):
  ALL = "all"
  ACTIVE = "active"
  INACTIVE = "inactive"


def apply_lifecycle_filter(query, model, status: LifecycleStatusFilter):
  """Filter an entity with an ``is_active`` lifecycle column."""
  if status == LifecycleStatusFilter.ACTIVE:
    return query.where(model.is_active.is_(True))
  if status == LifecycleStatusFilter.INACTIVE:
    return query.where(model.is_active.is_(False))
  return query
