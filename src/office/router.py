import uuid
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from src.core.database import get_db
from src.auth.dependencies import role_required, get_current_user
from src.user.models import Role, User
from src.office.schemas import (
  OfficeCreate,
  OfficeDeactivateRequest,
  OfficeHistoryResponse,
  OfficeResponse,
  OfficeUpdate,
)
from src.office.service import OfficeService
from src.core.filters import get_bbox_filter, LifecycleStatusFilter

router = APIRouter()


# --- Public Endpoints (no auth required) ---

@router.get("", response_model=List[OfficeResponse])
async def get_all_offices(
  q: Optional[str] = Query(None, description="Search term for office name or description"),
  bbox: Optional[Tuple[float, float, float, float]] = Depends(get_bbox_filter),
  skip: int = 0,
  limit: int = 100,
  status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
  db: AsyncSession = Depends(get_db),
):
  """
  Retrieves a list of active offices. 
  Publicly accessible.
  """
  return await OfficeService.get_all_offices(
    db=db, skip=skip, limit=limit, status=status, search=q, bbox=bbox
  )


@router.get("/{office_id}", response_model=OfficeResponse)
async def get_office(
  office_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
):
  """
  Retrieves specific details of a single office.
  Publicly accessible.
  """
  return await OfficeService.get_office_by_id(db, office_id)


# --- Admin Endpoints ---

@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(
  office_data: OfficeCreate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
):
  """
  Creates a new office/department.
  Strictly restricted to administrators.
  """
  return await OfficeService.create_office(db, office_data, current_user.id)


@router.patch("/{office_id}", response_model=OfficeResponse)
async def update_office(
  office_id: uuid.UUID,
  update_data: OfficeUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
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
  request: OfficeDeactivateRequest,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
):
  """
  Soft-deletes (deactivates) an office.
  Strictly restricted to administrators.
  """
  await OfficeService.deactivate_office(
    db,
    office_id,
    current_user.id,
    request.change_reason,
  )


@router.get("/{office_id}/history", response_model=List[OfficeHistoryResponse])
async def get_office_history(
  office_id: uuid.UUID,
  start_date: Optional[datetime] = Query(None, description="Start of the validity period"),
  end_date: Optional[datetime] = Query(None, description="End of the validity period"),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(Role.ADMIN))
):
  """
  Retrieves the audit trail/history for a specific office.
  Strictly restricted to administrators.
  """
  return await OfficeService.get_office_history(db, office_id, start_date, end_date)