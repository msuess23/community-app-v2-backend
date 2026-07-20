"""HTTP routes for appointment slots and event-sourced bookings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from src.appointment.domain import (
  AppointmentDocumentType,
  AppointmentSlotSortField,
  AppointmentSlotStatus,
  AppointmentSortField,
  AppointmentStatus,
)
from src.appointment.schemas import (
  AppointmentBookRequest,
  AppointmentCancelRequest,
  AppointmentCompleteRequest,
  AppointmentDocumentResponse,
  AppointmentEventResponse,
  AppointmentNoShowRequest,
  AppointmentRescheduleRequest,
  AppointmentResponse,
  AppointmentSlotBatchCreate,
  AppointmentSlotResponse,
)
from src.appointment.document_service import AppointmentDocumentService
from src.appointment.lifecycle_service import AppointmentLifecycleService
from src.appointment.service import AppointmentService
from src.appointment.slot_service import AppointmentSlotService
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
  "/appointments/{appointment_id}/documents",
  response_model=list[AppointmentDocumentResponse],
  tags=["Appointment Documents"],
)
async def list_appointment_documents(
  appointment_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """List current appointment documents visible to the current user."""

  return await AppointmentDocumentService.list_current(
    db,
    appointment_id=appointment_id,
    current_user=current_user,
  )


@router.post(
  "/appointments/{appointment_id}/documents",
  response_model=AppointmentDocumentResponse,
  status_code=status.HTTP_201_CREATED,
  tags=["Appointment Documents"],
)
async def upload_appointment_document(
  appointment_id: uuid.UUID,
  file: UploadFile = File(...),
  document_type: AppointmentDocumentType = Form(...),
  visible_to_citizen: bool = Form(False),
  replace_document_group_id: uuid.UUID | None = Form(None),
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """Create a document group or append the next immutable PDF version."""

  return await AppointmentDocumentService.upload_version(
    db,
    appointment_id=appointment_id,
    upload=file,
    document_type=document_type,
    visible_to_citizen=visible_to_citizen,
    replace_document_group_id=replace_document_group_id,
    current_user=current_user,
  )


@router.get(
  "/appointments/{appointment_id}/documents/{document_group_id}/versions",
  response_model=list[AppointmentDocumentResponse],
  tags=["Appointment Documents"],
)
async def list_appointment_document_versions(
  appointment_id: uuid.UUID,
  document_group_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(role_required(*CASE_WORKER_ROLES)),
):
  """List every retained version of one document group for office staff."""

  return await AppointmentDocumentService.list_versions(
    db,
    appointment_id=appointment_id,
    document_group_id=document_group_id,
    current_user=current_user,
  )


@router.get(
  "/appointments/{appointment_id}/documents/{document_version_id}/content",
  tags=["Appointment Documents"],
)
async def download_appointment_document(
  appointment_id: uuid.UUID,
  document_version_id: uuid.UUID,
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Download one authorized immutable appointment document version."""

  path, document = await AppointmentDocumentService.get_content(
    db,
    appointment_id=appointment_id,
    document_version_id=document_version_id,
    current_user=current_user,
  )
  return FileResponse(
    path,
    media_type=document.mime_type,
    filename=document.original_filename,
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
