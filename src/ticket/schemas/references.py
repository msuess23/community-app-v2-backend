"""Small data-minimizing references embedded in ticket API responses."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from src.user.models import Role


class OfficeReference(BaseModel):
  """Stable office label without exposing the full office resource."""

  id: UUID
  name: str


class UserReference(BaseModel):
  """Stable user label without account or contact information."""

  id: UUID
  display_name: str


class StaffUserReference(UserReference):
  """Authority user option enriched with role and office context."""

  role: Role
  office: OfficeReference | None = None
