"""HTTP routes for booking, querying and changing appointments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.appointment.domain import AppointmentSortField, AppointmentStatus
from src.appointment.lifecycle_service import AppointmentLifecycleService
from src.appointment.schemas import (
  AppointmentBookRequest,
  AppointmentCancelRequest,
  AppointmentCompleteRequest,
  AppointmentEventResponse,
  AppointmentNoShowRequest,
  AppointmentRescheduleRequest,
  AppointmentResponse,
)
from src.appointment.service import AppointmentService
from src.auth.dependencies import get_current_user, role_required
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


@router.post(
  "/appointments/{appointment_id}/reschedule",
  response_model=AppointmentResponse,
  tags=["Appointments"],
)
async def reschedule_appointment(
  appointment_id: uuid.UUID,
  request: AppointmentRescheduleRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Move an owned or office-managed appointment to another free slot."""

  return await AppointmentLifecycleService.reschedule(
    db,
    appointment_id=appointment_id,
    request=request,
    current_user=current_user,
  )


@router.post(
  "/appointments/{appointment_id}/cancel",
  response_model=AppointmentResponse,
  tags=["Appointments"],
)
async def cancel_appointment(
  appointment_id: uuid.UUID,
  request: AppointmentCancelRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Cancel an owned or office-managed future appointment."""

  return await AppointmentLifecycleService.cancel(
    db,
    appointment_id=appointment_id,
    request=request,
    current_user=current_user,
  )


@router.post(
  "/appointments/{appointment_id}/complete",
  response_model=AppointmentResponse,
  tags=["Appointments"],
)
async def complete_appointment(
  appointment_id: uuid.UUID,
  request: AppointmentCompleteRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Complete an appointment after its scheduled start."""

  return await AppointmentLifecycleService.complete(
    db,
    appointment_id=appointment_id,
    request=request,
    current_user=current_user,
  )


@router.post(
  "/appointments/{appointment_id}/no-show",
  response_model=AppointmentResponse,
  tags=["Appointments"],
)
async def mark_appointment_no_show(
  appointment_id: uuid.UUID,
  request: AppointmentNoShowRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Mark an appointment as a citizen no-show after its start."""

  return await AppointmentLifecycleService.mark_no_show(
    db,
    appointment_id=appointment_id,
    request=request,
    current_user=current_user,
  )


@router.get(
  "/appointments/{appointment_id}/events",
  response_model=PaginatedResponse[AppointmentEventResponse],
  tags=["Appointments"],
)
async def list_appointment_events(
  appointment_id: uuid.UUID,
  page_params: PageParams = Depends(get_page_params),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Return a chronological appointment event page to an authorized reader."""

  return await AppointmentService.get_events(
    db,
    appointment_id=appointment_id,
    current_user=current_user,
    page=page_params.page,
    size=page_params.size,
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
