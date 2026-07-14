import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import role_required
from src.core.database import get_db
from src.core.filters import LifecycleStatusFilter, get_bbox_filter
from src.office.schemas import (
  OfficeCreate,
  OfficeDeactivate,
  OfficeHistoryResponse,
  OfficeResponse,
  OfficeUpdate,
)
from src.office.service import OfficeService
from src.user.models import User


router = APIRouter()


@router.get("", response_model=List[OfficeResponse])
async def get_all_offices(
  q: Optional[str] = Query(None),
  bbox: Optional[Tuple[float, float, float, float]] = Depends(get_bbox_filter),
  skip: int = 0,
  limit: int = 100,
  status_filter: LifecycleStatusFilter = Query(
    LifecycleStatusFilter.ACTIVE,
    alias="status",
  ),
  db: AsyncSession = Depends(get_db),
):
  return await OfficeService.get_all_offices(
    db=db,
    skip=skip,
    limit=limit,
    status=status_filter,
    search=q,
    bbox=bbox,
  )


@router.get("/{office_id}", response_model=OfficeResponse)
async def get_office(
  office_id: uuid.UUID,
  db: AsyncSession = Depends(get_db),
):
  return await OfficeService.get_office_by_id(db, office_id)


@router.post("", response_model=OfficeResponse, status_code=status.HTTP_201_CREATED)
async def create_office(
  office_data: OfficeCreate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])),
):
  return await OfficeService.create_office(db, office_data, current_user.id)


@router.patch("/{office_id}", response_model=OfficeResponse)
async def update_office(
  office_id: uuid.UUID,
  update_data: OfficeUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])),
):
  target_office = await OfficeService.get_office_by_id(db, office_id)
  return await OfficeService.update_office(
    db,
    target_office,
    update_data,
    current_user.id,
  )


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_office(
  office_id: uuid.UUID,
  command: OfficeDeactivate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])),
):
  await OfficeService.deactivate_office(
    db,
    office_id,
    current_user.id,
    change_reason=command.change_reason,
  )


@router.get("/{office_id}/history", response_model=List[OfficeHistoryResponse])
async def get_office_history(
  office_id: uuid.UUID,
  start_date: Optional[datetime] = Query(None),
  end_date: Optional[datetime] = Query(None),
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(role_required(["ADMIN"])),
):
  return await OfficeService.get_office_history(
    db,
    office_id,
    start_date,
    end_date,
  )
