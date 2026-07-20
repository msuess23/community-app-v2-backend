"""HTTP routes for immutable appointment document versions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.appointment.document_service import AppointmentDocumentService
from src.appointment.domain import AppointmentDocumentType
from src.appointment.schemas import AppointmentDocumentResponse
from src.auth.dependencies import get_current_user, role_required
from src.core.database import get_db
from src.user.models import User
from src.user.roles import CASE_WORKER_ROLES
from starlette.responses import FileResponse

router = APIRouter()


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
