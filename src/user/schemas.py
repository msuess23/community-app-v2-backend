from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.request_models import StrictRequestModel
from src.core.schemas import BaseMetadataResponse
from src.core.security import ensure_bcrypt_compatible, normalize_email
from src.core.validation import (
  ChangeReason,
  NonNullableNormalizedUpdateText,
  NormalizedRequiredText,
)
from src.user.models import Role


class UserCreate(StrictRequestModel):

  """Validate account registration and administrative user creation."""

  email: EmailStr
  password: str = Field(..., min_length=8, max_length=128)
  first_name: NormalizedRequiredText = Field(..., min_length=2, max_length=100)
  last_name: NormalizedRequiredText = Field(..., min_length=2, max_length=100)

  @field_validator("email")
  @classmethod
  def normalize_email_value(cls, value: EmailStr) -> str:
    """Normalize the account email before uniqueness validation."""

    return normalize_email(str(value))

  @field_validator("password")
  @classmethod
  def validate_password_bytes(cls, value: str) -> str:
    """Reject passwords that exceed the bcrypt byte limit."""

    return ensure_bcrypt_compatible(value)


class UserResponse(BaseMetadataResponse):
  """Serialize the current public user account state."""

  id: UUID
  email: EmailStr
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None

  model_config = ConfigDict(from_attributes=True)


class UserUpdate(StrictRequestModel):
  """Validate fields a user may change on their own profile."""

  first_name: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=2,
    max_length=100,
  )
  last_name: NonNullableNormalizedUpdateText = Field(
    None,
    min_length=2,
    max_length=100,
  )


class AdminUserUpdate(UserUpdate):
  """Validate administrative role, office, and profile changes."""

  role: Optional[Role] = None
  office_id: Optional[UUID] = None
  change_reason: ChangeReason

  @field_validator("role", mode="before")
  @classmethod
  def reject_null_role(cls, value: object) -> object:
    """Reject explicit null for the non-nullable role field."""

    if value is None:
      raise ValueError("role cannot be null")
    return value


class UserDeactivateRequest(StrictRequestModel):
  """Validate the audit reason for user deactivation."""

  change_reason: ChangeReason


class UserHistoryResponse(BaseModel):
  """Serialize one immutable user history snapshot."""

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
