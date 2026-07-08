from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime

from src.address.schemas import AddressCreate, AddressUpdate, AddressResponse

class OfficeCreate(BaseModel):
  """
  Schema for creating a new office.
  Restricted to administrators.
  """
  name: str = Field(..., min_length=3, max_length=150, description="Official name of the office/department")
  description: Optional[str] = Field(None, max_length=500, description="Optional details about the office's responsibilities")

class OfficeUpdate(BaseModel):
  """
  Schema for updating an existing office.
  All fields are optional to allow partial updates (PATCH).
  """
  name: Optional[str] = Field(None, min_length=3, max_length=150)
  description: Optional[str] = Field(None, max_length=500)
  address: Optional[AddressCreate] = None

class OfficeResponse(BaseModel):
  """
  Schema for returning office data to the client.
  """
  id: UUID
  name: str
  description: Optional[str] = None
  is_active: bool
  created_at: datetime
  deactivated_at: Optional[datetime] = None
  address: Optional[AddressResponse] = None
  model_config = ConfigDict(from_attributes=True)