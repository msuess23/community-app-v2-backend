from datetime import datetime
from math import ceil
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator


T = TypeVar("T")


class EntityMetadata(BaseModel):
  """Administrative lifecycle metadata exposed with API resources."""

  is_active: bool
  created_at: datetime
  deactivated_at: Optional[datetime] = None


class BaseMetadataResponse(BaseModel):
  """Maps flat ORM lifecycle fields into a nested metadata object."""

  metadata: EntityMetadata

  @model_validator(mode="before")
  @classmethod
  def map_metadata(cls, data: Any) -> Any:
    if isinstance(data, dict):
      if "metadata" not in data:
        data["metadata"] = {
          "is_active": data.get("is_active", True),
          "created_at": data.get("created_at"),
          "deactivated_at": data.get("deactivated_at"),
        }
      return data

    result = {
      key: value
      for key, value in data.__dict__.items()
      if not key.startswith("_")
    }
    result["metadata"] = {
      "is_active": getattr(data, "is_active", True),
      "created_at": getattr(data, "created_at", None),
      "deactivated_at": getattr(data, "deactivated_at", None),
    }
    return result


class PaginatedResponse(BaseModel, Generic[T]):
  """Common response contract for page-based list endpoints."""

  data: list[T]
  total: int = Field(ge=0)
  page: int = Field(ge=1)
  size: int = Field(ge=1)
  pages: int = Field(ge=0)

  @classmethod
  def create(
    cls,
    *,
    data: list[T],
    total: int,
    page: int,
    size: int,
  ) -> "PaginatedResponse[T]":
    pages = ceil(total / size) if total else 0
    return cls(data=data, total=total, page=page, size=size, pages=pages)
