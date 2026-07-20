"""Versioned PDF document commands and access-controlled reads for appointments."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.access_policy import AppointmentAccessPolicy
from src.appointment.domain import (
  AppointmentDocumentType,
  AppointmentEventType,
  DocumentVersionAddedPayload,
)
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment, AppointmentDocument
from src.appointment.repository import (
  AppointmentDocumentRepository,
  AppointmentRepository,
)
from src.appointment.schemas import AppointmentDocumentResponse
from src.core.config import settings
from src.core.exceptions import ForbiddenException, ResourceNotFoundException
from src.core.transaction_files import (
  register_rollback_file,
  unregister_rollback_file,
)
from src.media.document_storage import (
  DocumentStorageConfig,
  DocumentStorageErrorCodes,
  LocalDocumentStorage,
)
from src.user.models import Role, User


class AppointmentDocumentService:
  """Coordinate appointment authorization, PDF versions and audit events."""

  @staticmethod
  def _storage_config() -> DocumentStorageConfig:
    """Build the appointment-specific configuration for shared PDF storage."""

    return DocumentStorageConfig(
      root=settings.APPOINTMENT_DOCUMENT_ROOT,
      max_bytes=settings.APPOINTMENT_DOCUMENT_MAX_BYTES,
      fallback_filename="appointment-document.pdf",
      subject="appointment",
      errors=DocumentStorageErrorCodes(
        unsupported_type="UNSUPPORTED_APPOINTMENT_DOCUMENT_TYPE",
        too_large="APPOINTMENT_DOCUMENT_TOO_LARGE",
        empty="EMPTY_APPOINTMENT_DOCUMENT",
        invalid_content="INVALID_APPOINTMENT_DOCUMENT_CONTENT",
        file_not_found="APPOINTMENT_DOCUMENT_FILE_NOT_FOUND",
      ),
    )

  @staticmethod
  def _document_url(
    appointment_id: uuid.UUID,
    document_version_id: uuid.UUID,
  ) -> str:
    """Build the stable API URL for one immutable document version."""

    return (
      f"{settings.BASE_URL}/appointments/{appointment_id}/documents/"
      f"{document_version_id}/content"
    )

  @staticmethod
  def _response(document: AppointmentDocument) -> AppointmentDocumentResponse:
    """Map one document version to public metadata without staff identifiers."""

    return AppointmentDocumentResponse(
      id=document.id,
      document_group_id=document.document_group_id,
      appointment_id=document.appointment_id,
      version_number=document.version_number,
      document_type=document.document_type,
      original_filename=document.original_filename,
      mime_type=document.mime_type,
      size_bytes=document.size_bytes,
      uploaded_at=document.uploaded_at,
      is_current=document.is_current,
      visible_to_citizen=document.visible_to_citizen,
      replaced_version_id=document.replaced_version_id,
      url=AppointmentDocumentService._document_url(
        document.appointment_id,
        document.id,
      ),
    )

  @staticmethod
  async def _require_appointment(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> Appointment:
    """Load one appointment or raise the canonical not-found response."""

    appointment = await AppointmentRepository.get_by_id(
      db,
      appointment_id,
      for_update=for_update,
    )
    if appointment is None:
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )
    return appointment

  @staticmethod
  def _require_staff_access(
    appointment: Appointment,
    current_user: User,
  ) -> None:
    """Require an active case worker from the appointment's owning office."""

    if not AppointmentAccessPolicy.can_manage_office(
      appointment.office_id,
      current_user,
    ):
      raise ForbiddenException(
        "Only the responsible office may manage appointment documents"
      )

  @staticmethod
  async def upload_version(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    upload: UploadFile,
    document_type: AppointmentDocumentType,
    visible_to_citizen: bool,
    replace_document_group_id: uuid.UUID | None,
    current_user: User,
  ) -> AppointmentDocumentResponse:
    """Add a new PDF group or append the next immutable group version."""

    appointment = await AppointmentDocumentService._require_appointment(
      db,
      appointment_id,
      for_update=True,
    )
    AppointmentDocumentService._require_staff_access(appointment, current_user)

    replaced: AppointmentDocument | None = None
    if replace_document_group_id is not None:
      replaced = await AppointmentDocumentRepository.get_current_for_group(
        db,
        appointment_id=appointment.id,
        document_group_id=replace_document_group_id,
        for_update=True,
      )
      if replaced is None:
        raise ResourceNotFoundException(
          "Appointment document group not found",
          error_code="APPOINTMENT_DOCUMENT_GROUP_NOT_FOUND",
        )

    document_group_id = (
      replaced.document_group_id if replaced is not None else uuid.uuid4()
    )
    version_number = replaced.version_number + 1 if replaced is not None else 1
    document_id = uuid.uuid4()
    storage_config = AppointmentDocumentService._storage_config()
    stored = await LocalDocumentStorage.save_upload(
      upload,
      owner_path=f"{appointment.id}/{document_group_id}",
      document_id=document_id,
      config=storage_config,
    )
    stored_path = LocalDocumentStorage.resolve_file(
      stored.storage_key,
      config=storage_config,
    )
    register_rollback_file(db, stored_path)

    try:
      event = await AppointmentEventStore.append(
        db,
        appointment,
        actor_user_id=current_user.id,
        event_type=AppointmentEventType.DOCUMENT_VERSION_ADDED,
        payload=DocumentVersionAddedPayload(
          document_group_id=document_group_id,
          document_version_id=document_id,
          version_number=version_number,
          document_type=document_type,
          storage_key=stored.storage_key,
          original_filename=stored.original_filename,
          mime_type=stored.mime_type,
          size_bytes=stored.size_bytes,
          visible_to_citizen=visible_to_citizen,
          replaced_version_id=(replaced.id if replaced is not None else None),
        ),
      )
      if replaced is not None:
        # Release the partial one-current-version unique index before inserting
        # the replacement. This must not depend on ORM statement ordering.
        replaced.is_current = False
        await db.flush()

      document = AppointmentDocument(
        id=document_id,
        document_group_id=document_group_id,
        appointment_id=appointment.id,
        version_number=version_number,
        document_type=document_type,
        storage_key=stored.storage_key,
        original_filename=stored.original_filename,
        mime_type=stored.mime_type,
        size_bytes=stored.size_bytes,
        uploaded_by_user_id=current_user.id,
        uploaded_at=event.occurred_at,
        is_current=True,
        visible_to_citizen=visible_to_citizen,
        replaced_version_id=(replaced.id if replaced is not None else None),
      )
      AppointmentDocumentRepository.add(db, document)
      await db.flush()
    except Exception:
      LocalDocumentStorage.delete_file(stored.storage_key, config=storage_config)
      unregister_rollback_file(db, stored_path)
      raise

    return AppointmentDocumentService._response(document)

  @staticmethod
  async def list_current(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    current_user: User,
  ) -> list[AppointmentDocumentResponse]:
    """List current document groups with citizen visibility filtering."""

    appointment = await AppointmentDocumentService._require_appointment(
      db,
      appointment_id,
    )
    if not AppointmentAccessPolicy.can_view(appointment, current_user):
      raise ResourceNotFoundException(
        "Appointment not found",
        error_code="APPOINTMENT_NOT_FOUND",
      )

    visible_only = current_user.role == Role.CITIZEN
    documents = await AppointmentDocumentRepository.get_current_documents(
      db,
      appointment.id,
      visible_only=visible_only,
    )
    return [AppointmentDocumentService._response(item) for item in documents]

  @staticmethod
  async def list_versions(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    document_group_id: uuid.UUID,
    current_user: User,
  ) -> list[AppointmentDocumentResponse]:
    """List all retained versions for authorized office staff."""

    appointment = await AppointmentDocumentService._require_appointment(
      db,
      appointment_id,
    )
    AppointmentDocumentService._require_staff_access(appointment, current_user)
    documents = await AppointmentDocumentRepository.get_versions(
      db,
      appointment_id=appointment.id,
      document_group_id=document_group_id,
    )
    if not documents:
      raise ResourceNotFoundException(
        "Appointment document group not found",
        error_code="APPOINTMENT_DOCUMENT_GROUP_NOT_FOUND",
      )
    return [AppointmentDocumentService._response(item) for item in documents]

  @staticmethod
  async def get_content(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    document_version_id: uuid.UUID,
    current_user: User,
  ) -> tuple[Path, AppointmentDocument]:
    """Resolve one current citizen document or any staff-visible version."""

    appointment = await AppointmentDocumentService._require_appointment(
      db,
      appointment_id,
    )
    document = await AppointmentDocumentRepository.get_by_id(
      db,
      appointment_id=appointment.id,
      document_version_id=document_version_id,
    )
    if document is None:
      raise ResourceNotFoundException(
        "Appointment document not found",
        error_code="APPOINTMENT_DOCUMENT_NOT_FOUND",
      )

    if current_user.role == Role.CITIZEN:
      if not AppointmentAccessPolicy.is_owner(appointment, current_user):
        raise ResourceNotFoundException(
          "Appointment document not found",
          error_code="APPOINTMENT_DOCUMENT_NOT_FOUND",
        )
      if not document.is_current or not document.visible_to_citizen:
        raise ResourceNotFoundException(
          "Appointment document not found",
          error_code="APPOINTMENT_DOCUMENT_NOT_FOUND",
        )
    else:
      AppointmentDocumentService._require_staff_access(appointment, current_user)

    path = LocalDocumentStorage.resolve_file(
      document.storage_key,
      config=AppointmentDocumentService._storage_config(),
    )
    return path, document
