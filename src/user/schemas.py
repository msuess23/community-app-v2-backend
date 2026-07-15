from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.schemas import BaseMetadataResponse
from src.core.security import ensure_bcrypt_compatible, normalize_email
from src.user.models import Role


def _normalize_name(value: str) -> str:
  normalized = " ".join(value.split())
  if len(normalized) < 2:
    raise ValueError("name must contain at least 2 characters")
  return normalized


class UserCreate(BaseModel):
  model_config = ConfigDict(extra="forbid")

  email: EmailStr
  password: str = Field(..., min_length=8, max_length=128)
  first_name: str = Field(..., min_length=2, max_length=100)
  last_name: str = Field(..., min_length=2, max_length=100)

  @field_validator("email")
  @classmethod
  def normalize_email_value(cls, value: EmailStr) -> str:
    return normalize_email(str(value))

  @field_validator("password")
  @classmethod
  def validate_password_bytes(cls, value: str) -> str:
    return ensure_bcrypt_compatible(value)

  @field_validator("first_name", "last_name")
  @classmethod
  def normalize_names(cls, value: str) -> str:
    return _normalize_name(value)


class UserResponse(BaseMetadataResponse):
  id: UUID
  email: EmailStr
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None

  model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
  first_name: Optional[str] = Field(None, min_length=2, max_length=100)
  last_name: Optional[str] = Field(None, min_length=2, max_length=100)

  @field_validator("first_name", "last_name")
  @classmethod
  def normalize_names(cls, value: Optional[str]) -> Optional[str]:
    return _normalize_name(value) if value is not None else None


class AdminUserUpdate(UserUpdate):
  role: Optional[Role] = None
  office_id: Optional[UUID] = None
  change_reason: str = Field(..., min_length=3, max_length=500)

  @field_validator("change_reason")
  @classmethod
  def normalize_change_reason(cls, value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) < 3:
      raise ValueError("change_reason must contain at least 3 characters")
    return normalized


class UserDeactivateRequest(BaseModel):
  change_reason: str = Field(..., min_length=3, max_length=500)

  @field_validator("change_reason")
  @classmethod
  def normalize_change_reason(cls, value: str) -> str:
    normalized = " ".join(value.split())
    if len(normalized) < 3:
      raise ValueError("change_reason must contain at least 3 characters")
    return normalized


class UserHistoryResponse(BaseModel):
  id: UUID
  user_id: UUID
  email: str
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None
  is_active: bool
  changed_by_user_id: UUID
  change_reason: str
  changed_at: datetime

  model_config = ConfigDict(from_attributes=True)
