from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

from src.user.models import Role
from src.core.schemas import BaseMetadataResponse
from src.core.validation import PasswordValue

class UserCreate(BaseModel):
  email: EmailStr
  password: PasswordValue
  first_name: str = Field(..., min_length=2)
  last_name: str = Field(..., min_length=2)

class UserResponse(BaseMetadataResponse):
  id: UUID
  email: EmailStr
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None
  
  model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
  """
  Fields that a standard user is allowed to update on their own profile.
  """
  first_name: Optional[str] = Field(None, min_length=2)
  last_name: Optional[str] = Field(None, min_length=2)

class AdminUserUpdate(UserUpdate):
  """
  Fields that an administrator is allowed to update on any user profile.
  Inherits from UserUpdate to include first_name and last_name.
  """
  role: Optional[Role] = None
  office_id: Optional[UUID] = None


class UserHistoryResponse(BaseModel):
  id: UUID
  user_id: UUID
  email: str
  first_name: str
  last_name: str
  role: Role
  changed_by_user_id: UUID
  change_reason: str
  changed_at: datetime
  model_config = ConfigDict(from_attributes=True)