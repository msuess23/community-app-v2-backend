"""Versioning and visibility tests for appointment PDF documents."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.appointment.document_service import AppointmentDocumentService
from src.appointment.domain import AppointmentDocumentType, AppointmentEventType
from src.appointment.models import Appointment, AppointmentDocument, AppointmentEvent
from src.appointment.repository import (
  AppointmentDocumentRepository,
  AppointmentRepository,
)
from src.media.document_storage import StoredDocument
from src.user.models import Role, User


def _user(role: Role, *, office_id=None, user_id=None) -> User:
  return User(
    id=user_id or uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="hash",
    first_name="Document",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _appointment(citizen_id, office_id) -> Appointment:
  starts = datetime.now(timezone.utc) + timedelta(days=1)
  return Appointment(
    id=uuid.uuid4(),
    current_slot_id=uuid.uuid4(),
    office_id=office_id,
    citizen_id=citizen_id,
    status="SCHEDULED",
    starts_at=starts,
    ends_at=starts + timedelta(minutes=30),
    version=1,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
  )


def _db() -> MagicMock:
  db = MagicMock()
  db.info = {}
  db.flush = AsyncMock()
  return db


@pytest.mark.asyncio
async def test_upload_creates_first_document_version_and_event(monkeypatch, tmp_path) -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  manager = _user(Role.MANAGER, office_id=office_id)
  appointment = _appointment(citizen.id, office_id)
  stored_path = tmp_path / "document.pdf"
  stored_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
  staged: list[AppointmentDocument] = []
  event = AppointmentEvent(
    id=uuid.uuid4(),
    appointment_id=appointment.id,
    sequence_number=2,
    event_type=AppointmentEventType.DOCUMENT_VERSION_ADDED,
    actor_user_id=manager.id,
    occurred_at=datetime.now(timezone.utc),
    payload={},
  )

  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.save_upload",
    AsyncMock(
      return_value=StoredDocument(
        storage_key="appointment/group/document.pdf",
        original_filename="notice.pdf",
        mime_type="application/pdf",
        size_bytes=100,
      )
    ),
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.resolve_file",
    lambda *args, **kwargs: stored_path,
  )
  append = AsyncMock(return_value=event)
  monkeypatch.setattr(
    "src.appointment.document_service.AppointmentEventStore.append",
    append,
  )
  monkeypatch.setattr(
    AppointmentDocumentRepository,
    "add",
    lambda _db, document: staged.append(document),
  )

  response = await AppointmentDocumentService.upload_version(
    _db(),
    appointment_id=appointment.id,
    upload=object(),
    document_type=AppointmentDocumentType.NOTICE,
    visible_to_citizen=True,
    replace_document_group_id=None,
    current_user=manager,
  )

  assert response.version_number == 1
  assert response.visible_to_citizen is True
  assert len(staged) == 1
  assert staged[0].is_current is True
  assert append.await_args.kwargs["event_type"] == AppointmentEventType.DOCUMENT_VERSION_ADDED
  assert append.await_args.kwargs["payload"].storage_key.endswith("document.pdf")


@pytest.mark.asyncio
async def test_replacement_retains_old_version_and_increments_number(
  monkeypatch,
  tmp_path,
) -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  manager = _user(Role.MANAGER, office_id=office_id)
  appointment = _appointment(citizen.id, office_id)
  group_id = uuid.uuid4()
  previous = AppointmentDocument(
    id=uuid.uuid4(),
    document_group_id=group_id,
    appointment_id=appointment.id,
    version_number=1,
    document_type=AppointmentDocumentType.FORM,
    storage_key="old.pdf",
    original_filename="old.pdf",
    mime_type="application/pdf",
    size_bytes=10,
    uploaded_by_user_id=manager.id,
    uploaded_at=datetime.now(timezone.utc),
    is_current=True,
    visible_to_citizen=False,
  )
  stored_path = tmp_path / "new.pdf"
  stored_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
  event = AppointmentEvent(
    id=uuid.uuid4(),
    appointment_id=appointment.id,
    sequence_number=2,
    event_type=AppointmentEventType.DOCUMENT_VERSION_ADDED,
    actor_user_id=manager.id,
    occurred_at=datetime.now(timezone.utc),
    payload={},
  )
  staged: list[AppointmentDocument] = []

  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  monkeypatch.setattr(
    AppointmentDocumentRepository,
    "get_current_for_group",
    AsyncMock(return_value=previous),
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.save_upload",
    AsyncMock(
      return_value=StoredDocument(
        storage_key="new.pdf",
        original_filename="new.pdf",
        mime_type="application/pdf",
        size_bytes=20,
      )
    ),
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.resolve_file",
    lambda *args, **kwargs: stored_path,
  )
  monkeypatch.setattr(
    "src.appointment.document_service.AppointmentEventStore.append",
    AsyncMock(return_value=event),
  )
  monkeypatch.setattr(
    AppointmentDocumentRepository,
    "add",
    lambda _db, document: staged.append(document),
  )
  db = _db()

  response = await AppointmentDocumentService.upload_version(
    db,
    appointment_id=appointment.id,
    upload=object(),
    document_type=AppointmentDocumentType.FORM,
    visible_to_citizen=True,
    replace_document_group_id=group_id,
    current_user=manager,
  )

  assert previous.is_current is False
  assert response.document_group_id == group_id
  assert response.version_number == 2
  assert response.replaced_version_id == previous.id
  assert staged[0].is_current is True
  assert db.flush.await_count == 2


@pytest.mark.asyncio
async def test_citizen_list_requests_only_current_visible_documents(monkeypatch) -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  appointment = _appointment(citizen.id, office_id)
  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  get_documents = AsyncMock(return_value=[])
  monkeypatch.setattr(
    AppointmentDocumentRepository,
    "get_current_documents",
    get_documents,
  )

  result = await AppointmentDocumentService.list_current(
    _db(),
    appointment_id=appointment.id,
    current_user=citizen,
  )

  assert result == []
  assert get_documents.await_args.kwargs["visible_only"] is True


@pytest.mark.asyncio
async def test_upload_failure_removes_new_file(monkeypatch, tmp_path) -> None:
  office_id = uuid.uuid4()
  citizen = _user(Role.CITIZEN)
  manager = _user(Role.MANAGER, office_id=office_id)
  appointment = _appointment(citizen.id, office_id)
  stored_path = tmp_path / "failed.pdf"
  stored_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
  delete_file = MagicMock(side_effect=lambda *args, **kwargs: stored_path.unlink())

  monkeypatch.setattr(
    AppointmentRepository,
    "get_by_id",
    AsyncMock(return_value=appointment),
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.save_upload",
    AsyncMock(
      return_value=StoredDocument(
        storage_key="failed.pdf",
        original_filename="failed.pdf",
        mime_type="application/pdf",
        size_bytes=20,
      )
    ),
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.resolve_file",
    lambda *args, **kwargs: stored_path,
  )
  monkeypatch.setattr(
    "src.appointment.document_service.LocalDocumentStorage.delete_file",
    delete_file,
  )
  monkeypatch.setattr(
    "src.appointment.document_service.AppointmentEventStore.append",
    AsyncMock(side_effect=RuntimeError("event write failed")),
  )

  with pytest.raises(RuntimeError, match="event write failed"):
    await AppointmentDocumentService.upload_version(
      _db(),
      appointment_id=appointment.id,
      upload=object(),
      document_type=AppointmentDocumentType.NOTICE,
      visible_to_citizen=False,
      replace_document_group_id=None,
      current_user=manager,
    )

  delete_file.assert_called_once()
  assert not stored_path.exists()
