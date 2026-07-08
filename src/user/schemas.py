from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

from src.user.models import Role

class UserCreate(BaseModel):
  email: EmailStr
  password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
  first_name: str = Field(..., min_length=2)
  last_name: str = Field(..., min_length=2)

class UserResponse(BaseModel):
  id: UUID
  email: EmailStr
  first_name: str
  last_name: str
  role: Role
  office_id: Optional[UUID] = None
  is_active: bool
  created_at: datetime
  deactivated_at: Optional[datetime] = None
  
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