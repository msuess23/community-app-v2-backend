import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.auth.dependencies import role_required
from src.user.models import User
from src.office.schemas import OfficeCreate, OfficeUpdate, OfficeResponse
from src.office.service import OfficeService

router = APIRouter()

@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(
  office_data: OfficeCreate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"]))
):
  """
  Creates a new office/department.
  Strictly restricted to administrators.
  """
  return await OfficeService.create_office(db, office_data, current_user.id)

@router.get("", response_model=List[OfficeResponse])
async def get_all_offices(
  skip: int = 0,
  limit: int = 100,
  include_inactive: bool = False,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN", "MANAGER", "DISPATCHER", "OFFICER"]))
):
  """
  Retrieves a list of offices.
  Accessible by all internal authority personnel for routing and assignment purposes.
  By default, deactivated offices are excluded unless explicitly requested.
  """
  return await OfficeService.get_all_offices(db, skip, limit, include_inactive)

@router.get("/{office_id}", response_model=OfficeResponse)
async def get_office(
  office_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN", "MANAGER", "DISPATCHER", "OFFICER"]))
):
  """
  Retrieves specific details of a single office.
  Accessible by all internal authority personnel.
  """
  return await OfficeService.get_office_by_id(db, office_id)

@router.patch("/{office_id}", response_model=OfficeResponse)
async def update_office(
  office_id: uuid.UUID,
  update_data: OfficeUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"]))
):
  """
  Updates details of an existing office.
  Triggers a history snapshot. Strictly restricted to administrators.
  """
  # Fetch the existing office first
  target_office = await OfficeService.get_office_by_id(db, office_id)
  
  # Apply updates via the service
  return await OfficeService.update_office(db, target_office, update_data, current_user.id)

@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_office(
  office_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"]))
):
  """
  Soft-deletes (deactivates) an office.
  Strictly restricted to administrators.
  """
  await OfficeService.deactivate_office(db, office_id, current_user.id)