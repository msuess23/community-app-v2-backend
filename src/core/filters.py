from enum import Enum
from typing import Optional, Tuple

from fastapi import HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.sql import Select


class LifecycleStatusFilter(str, Enum):
  ALL = "all"
  ACTIVE = "active"
  INACTIVE = "inactive"


class SortOrder(str, Enum):
  ASC = "asc"
  DESC = "desc"


async def get_bbox_filter(
  bbox: Optional[str] = Query(
    None,
    description="Bounding Box: minLon,minLat,maxLon,maxLat",
  ),
) -> Optional[Tuple[float, float, float, float]]:
  """Parses and validates a WGS84 bounding box."""
  if not bbox:
    return None

  try:
    coords = [float(value.strip()) for value in bbox.split(",")]
  except ValueError as exc:
    raise HTTPException(
      status_code=400,
      detail="Invalid bbox format. Expected: minLon,minLat,maxLon,maxLat",
    ) from exc

  if len(coords) != 4:
    raise HTTPException(
      status_code=400,
      detail="bbox must contain exactly 4 comma-separated coordinates",
    )

  min_lon, min_lat, max_lon, max_lat = coords
  if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
    raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
  if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
    raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
  if min_lon > max_lon or min_lat > max_lat:
    raise HTTPException(
      status_code=400,
      detail="Bounding box minimum values must not exceed maximum values",
    )

  return min_lon, min_lat, max_lon, max_lat


def apply_bbox_filter(
  query: Select,
  address_model,
  bbox: Optional[Tuple[float, float, float, float]],
) -> Select:
  if not bbox:
    return query

  min_lon, min_lat, max_lon, max_lat = bbox
  return query.where(
    address_model.latitude >= min_lat,
    address_model.latitude <= max_lat,
    address_model.longitude >= min_lon,
    address_model.longitude <= max_lon,
  )


def escape_like_pattern(value: str) -> str:
  """Escapes SQL LIKE wildcards so searches treat user input literally."""
  return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def apply_search_filter(query: Select, search_term: Optional[str], *columns) -> Select:
  if not search_term or not search_term.strip():
    return query

  term = f"%{escape_like_pattern(search_term.strip())}%"
  return query.where(or_(*[column.ilike(term, escape="\\") for column in columns]))


def apply_lifecycle_filter(query: Select, model, status: LifecycleStatusFilter) -> Select:
  if status == LifecycleStatusFilter.ACTIVE:
    return query.where(model.is_active.is_(True))
  if status == LifecycleStatusFilter.INACTIVE:
    return query.where(model.is_active.is_(False))
  return query
