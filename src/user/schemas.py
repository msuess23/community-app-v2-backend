from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

from src.core.normalization import normalize_email
from src.core.schemas import BaseMetadataResponse
from src.core.validation import PasswordValue
from src.user.models import Role


NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email)]
ChangeReason = Annotated[
  str,
  Field(
    min_length=3,
    max_length=500,
    description="Fachliche Begründung der administrativen Änderung",
  ),
]


class UserCreate(BaseModel):
  """Public citizen registration payload."""

  email: NormalizedEmail
  password: PasswordValue
  first_name: str = Field(..., min_length=2)
  last_name: str = Field(..., min_length=2)


class AdminUserCreate(BaseModel):
  """Administrative account creation, including role and office assignment."""

  email: NormalizedEmail
  password: PasswordValue
  first_name: str = Field(..., min_length=2)
  last_name: str = Field(..., min_length=2)
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

  first_name: Optional[str] = Field(None, min_length=2)
  last_name: Optional[str] = Field(None, min_length=2)
  change_reason: ChangeReason


class AdminUserUpdate(BaseModel):
  """Administrative partial update command for a user account."""

  first_name: Optional[str] = Field(None, min_length=2)
  last_name: Optional[str] = Field(None, min_length=2)
  role: Optional[Role] = None
  office_id: Optional[UUID] = None
  change_reason: ChangeReason


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

  model_config = ConfigDict(from_attributes=True)
