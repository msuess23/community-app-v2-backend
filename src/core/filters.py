from enum import Enum
from typing import Optional, Tuple
from fastapi import Query, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.sql import Select

# --- 1. FastAPI Route Dependencies ---

async def get_bbox_filter(
    bbox: Optional[str] = Query(None, description="Bounding Box: minLon,minLat,maxLon,maxLat")
) -> Optional[Tuple[float, float, float, float]]:
    """
    Parses the bbox query parameter from a comma-separated string into a typed Tuple.
    Throws a 400 Bad Request if the format is invalid.
    """
    if not bbox:
        return None
    try:
        coords = [float(c.strip()) for c in bbox.split(",")]
        if len(coords) == 4:
            return tuple(coords) # min_lon, min_lat, max_lon, max_lat
        raise HTTPException(status_code=400, detail="bbox must contain exactly 4 comma-separated coordinates")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid bbox format. Expected: minLon,minLat,maxLon,maxLat")


# --- 2. SQLAlchemy Query Helpers ---

def apply_bbox_filter(
    query: Select, 
    address_model, 
    bbox: Optional[Tuple[float, float, float, float]]
) -> Select:
    """
    Applies bounding box filtering to a SQLAlchemy query.
    Note: The caller must ensure that `address_model` is joined to the query beforehand.
    """
    if not bbox:
        return query
        
    min_lon, min_lat, max_lon, max_lat = bbox
    return query.where(
        address_model.latitude >= min_lat,
        address_model.latitude <= max_lat,
        address_model.longitude >= min_lon,
        address_model.longitude <= max_lon
    )

def apply_search_filter(query: Select, search_term: Optional[str], *columns) -> Select:
    """
    Applies a case-insensitive text search filter across multiple specified columns.
    """
    if not search_term:
        return query
        
    term = f"%{search_term}%"
    return query.where(or_(*[col.ilike(term) for col in columns]))


# --- Active/Inactive Filter for Users and Offices ---

class LifecycleStatusFilter(str, Enum):
    ALL = "all"
    ACTIVE = "active"
    INACTIVE = "inactive"

def apply_lifecycle_filter(query, model, status: LifecycleStatusFilter):
    """
    Helper function to filter based on is_active flag.
    Used for User and Office.
    """
    if status == LifecycleStatusFilter.ACTIVE:
        return query.where(model.is_active == True)
    elif status == LifecycleStatusFilter.INACTIVE:
        return query.where(model.is_active == False)
    return query