from __future__ import annotations

import math
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class SortOrder(str, Enum):
  ASC = "asc"
  DESC = "desc"


class PaginationParams(BaseModel):
  page: int = Field(1, ge=1)
  size: int = Field(20, ge=1, le=100)

  @property
  def offset(self) -> int:
    return (self.page - 1) * self.size


class Page(BaseModel, Generic[T]):
  data: list[T]
  total: int
  page: int
  size: int
  pages: int

  @classmethod
  def create(
    cls,
    *,
    data: list[T],
    total: int,
    pagination: PaginationParams,
  ) -> "Page[T]":
    pages = math.ceil(total / pagination.size) if total else 0
    return cls(
      data=data,
      total=total,
      page=pagination.page,
      size=pagination.size,
      pages=pages,
    )
