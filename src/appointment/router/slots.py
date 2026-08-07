"""HTTP routes for public and office-managed appointment slots."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.appointment.domain import AppointmentSlotSortField, AppointmentSlotStatus
from src.appointment.schemas import AppointmentSlotBatchCreate, AppointmentSlotResponse
from src.appointment.slot_service import AppointmentSlotService
from src.auth.dependencies import get_optional_current_user, role_required
from src.core.database import get_db
from src.core.filters import SortOrder
from src.core.query_params import (
  DateRangeParams,
  PageParams,
  get_page_params,
  get_starts_date_range,
)
from src.core.schemas import PaginatedResponse
from src.user.models import User
from src.user.roles import CASE_WORKER_ROLES

router = APIRouter()


@router.get(
  "/offices/{office_id}/appointment-slots",
  response_model=PaginatedResponse[AppointmentSlotResponse],
  tags=["Appointment Slots"],
)
async def list_appointment_slots(
  office_id: uuid.UUID,
  slot_status: AppointmentSlotStatus | None = Query(None, alias="status"),
  sort_by: AppointmentSlotSortField = AppointmentSlotSortField.STARTS_AT,
  order: SortOrder = SortOrder.ASC,
  starts_range: DateRangeParams = Depends(get_starts_date_range),
  page_params: PageParams = Depends(get_page_params),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User | None = Depends(get_optional_current_user),
):
  """List public availability or the owning office's complete slot view."""

  return await AppointmentSlotService.list_slots(
    db,
    office_id=office_id,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
    status=slot_status,
    starts_from=starts_range.start,
    starts_to=starts_range.end,
    sort_by=sort_by,
    order=order,
  )


@router.post(
  "/offices/{office_id}/appointment-slots",
  response_model=list[AppointmentSlotResponse],
  status_code=status.HTTP_201_CREATED,
  tags=["Appointment Slots"],
)
async def create_appointment_slots(
  office_id: uuid.UUID,
  request: AppointmentSlotBatchCreate,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Create a non-overlapping batch for the current case worker's office."""

  return await AppointmentSlotService.create_slots(
    db,
    office_id=office_id,
    request=request,
    current_user=current_user,
  )


@router.delete(
  "/offices/{office_id}/appointment-slots/{slot_id}",
  status_code=status.HTTP_204_NO_CONTENT,
  tags=["Appointment Slots"],
)
async def deactivate_appointment_slot(
  office_id: uuid.UUID,
  slot_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Deactivate one future available slot without deleting its row."""

  await AppointmentSlotService.deactivate_slot(
    db,
    office_id=office_id,
    slot_id=slot_id,
    current_user=current_user,
  )
