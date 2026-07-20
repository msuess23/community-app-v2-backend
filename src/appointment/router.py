"""HTTP routes for appointment slots and event-sourced bookings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.domain import (
  AppointmentSlotSortField,
  AppointmentSlotStatus,
  AppointmentSortField,
  AppointmentStatus,
)
from src.appointment.schemas import (
  AppointmentBookRequest,
  AppointmentResponse,
  AppointmentSlotBatchCreate,
  AppointmentSlotResponse,
)
from src.appointment.service import AppointmentService, AppointmentSlotService
from src.auth.dependencies import get_current_user, get_optional_current_user, role_required
from src.core.database import get_db
from src.core.filters import SortOrder
from src.core.query_params import (
  DateRangeParams,
  PageParams,
  SearchParams,
  get_created_date_range,
  get_page_params,
  get_search_params,
  get_starts_date_range,
)
from src.core.schemas import PaginatedResponse
from src.user.models import Role, User
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


@router.post(
  "/appointment-slots/{slot_id}/book",
  response_model=AppointmentResponse,
  status_code=status.HTTP_201_CREATED,
  tags=["Appointments"],
)
async def book_appointment_slot(
  slot_id: uuid.UUID,
  request: AppointmentBookRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """Book one available slot for the authenticated citizen."""

  return await AppointmentService.book_slot(
    db,
    slot_id=slot_id,
    request=request,
    current_user=current_user,
  )


@router.get(
  "/appointments/mine",
  response_model=PaginatedResponse[AppointmentResponse],
  tags=["Appointments"],
)
async def list_my_appointments(
  appointment_status: AppointmentStatus | None = Query(None, alias="status"),
  sort_by: AppointmentSortField = AppointmentSortField.STARTS_AT,
  order: SortOrder = SortOrder.ASC,
  starts_range: DateRangeParams = Depends(get_starts_date_range),
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(Role.CITIZEN)),
):
  """List appointments owned by the current citizen."""

  return await AppointmentService.list_mine(
    db,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
    status=appointment_status,
    starts_from=starts_range.start,
    starts_to=starts_range.end,
    search=search_params.q,
    sort_by=sort_by,
    order=order,
  )


@router.get(
  "/appointments/internal",
  response_model=PaginatedResponse[AppointmentResponse],
  tags=["Appointments"],
)
async def list_internal_appointments(
  office_id: uuid.UUID | None = Query(None),
  citizen_id: uuid.UUID | None = Query(None),
  ticket_id: uuid.UUID | None = Query(None),
  appointment_status: AppointmentStatus | None = Query(None, alias="status"),
  sort_by: AppointmentSortField = AppointmentSortField.STARTS_AT,
  order: SortOrder = SortOrder.ASC,
  starts_range: DateRangeParams = Depends(get_starts_date_range),
  created_range: DateRangeParams = Depends(get_created_date_range),
  page_params: PageParams = Depends(get_page_params),
  search_params: SearchParams = Depends(get_search_params),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Search appointments within the current case worker's office."""

  return await AppointmentService.list_internal(
    db,
    current_user=current_user,
    office_id=office_id,
    citizen_id=citizen_id,
    ticket_id=ticket_id,
    status=appointment_status,
    starts_from=starts_range.start,
    starts_to=starts_range.end,
    created_from=created_range.start,
    created_to=created_range.end,
    search=search_params.q,
    page=page_params.page,
    size=page_params.size,
    sort_by=sort_by,
    order=order,
  )


@router.get(
  "/appointments/{appointment_id}",
  response_model=AppointmentResponse,
  tags=["Appointments"],
)
async def get_appointment(
  appointment_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Return one appointment to its citizen or responsible office."""

  return await AppointmentService.get_appointment(
    db,
    appointment_id,
    current_user,
  )
