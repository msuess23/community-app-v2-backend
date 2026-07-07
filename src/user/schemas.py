from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

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
  role: str
  is_active: bool
  created_at: datetime
  
  # Tells Pydantic to read data even if it is not a dict, but an ORM model
  model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
  first_name: Optional[str] = Field(None, min_length=2)
  last_name: Optional[str] = Field(None, min_length=2)