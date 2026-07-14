from datetime import datetime
from enum import Enum
from typing import Annotated, Optional
from uuid import UUID

from pydantic import (
  BaseModel,
  BeforeValidator,
  ConfigDict,
  EmailStr,
  Field,
  model_validator,
)

from src.core.normalization import normalize_email, normalize_text
from src.core.schemas import BaseMetadataResponse
from src.core.validation import PasswordValue
from src.user.models import Role


NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email)]
PersonName = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(min_length=2, max_length=100),
]
ChangeReason = Annotated[
  str,
  BeforeValidator(normalize_text),
  Field(
    min_length=3,
    max_length=500,
    description="Fachliche Begründung der administrativen Änderung",
  ),
]


class UserSortField(str, Enum):
  LAST_NAME = "last_name"
  FIRST_NAME = "first_name"
  EMAIL = "email"
  CREATED_AT = "created_at"


class UserCreate(BaseModel):
  """Public citizen registration payload."""

  email: NormalizedEmail
  password: PasswordValue
  first_name: PersonName
  last_name: PersonName


class AdminUserCreate(BaseModel):
  """Administrative account creation, including role and office assignment."""

  email: NormalizedEmail
  password: PasswordValue
  first_name: PersonName
  last_name: PersonName
  role: Role
  office_id: Optional[UUID] = None
  change_reason: ChangeReason


class UserResponse(BaseMetadataResponse):
  id: UUID
  email: EmailStr
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None

  model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
  """Fields a user may change on their own profile plus an audit reason."""

  first_name: Optional[PersonName] = None
  last_name: Optional[PersonName] = None
  change_reason: ChangeReason

  @model_validator(mode="before")
  @classmethod
  def reject_null_names(cls, data):
    if isinstance(data, dict):
      for field in ("first_name", "last_name"):
        if field in data and data[field] is None:
          raise ValueError(f"{field} cannot be null")
    return data


class AdminUserUpdate(BaseModel):
  """Administrative partial update command for a user account."""

  first_name: Optional[PersonName] = None
  last_name: Optional[PersonName] = None
  role: Optional[Role] = None
  office_id: Optional[UUID] = None
  change_reason: ChangeReason

  @model_validator(mode="before")
  @classmethod
  def reject_null_non_nullable_fields(cls, data):
    if isinstance(data, dict):
      for field in ("first_name", "last_name", "role"):
        if field in data and data[field] is None:
          raise ValueError(f"{field} cannot be null")
    return data


class UserDeactivate(BaseModel):
  change_reason: ChangeReason


class UserHistoryResponse(BaseModel):
  id: UUID
  user_id: UUID
  email: str
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None
  is_active: bool
  deactivated_at: Optional[datetime] = None
  changed_by_user_id: UUID
  change_reason: str
  valid_from: datetime
  valid_to: Optional[datetime] = None
  anonymized_at: Optional[datetime] = None
  anonymized_by_user_id: Optional[UUID] = None
  anonymization_reason: Optional[str] = None

  model_config = ConfigDict(from_attributes=True)
