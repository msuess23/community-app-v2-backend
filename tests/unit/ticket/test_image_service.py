from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from src.core.config import settings
from src.core.exceptions import ConflictException
from src.ticket.events import TicketCategory, TicketWorkflowState
from src.ticket.image_service import TicketImageService
from src.ticket.media_storage import LocalTicketMediaStorage
from src.ticket.models import Ticket
from src.user.models import Role, User


def _citizen() -> User:
  return User(
    id=uuid4(),
    email="creator@example.com",
    hashed_password="hash",
    first_name="Ticket",
    last_name="Creator",
    role=Role.CITIZEN,
    is_active=True,
  )


def _ticket(citizen: User, state: TicketWorkflowState) -> Ticket:
  return Ticket(
    id=uuid4(),
    title="Road damage",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=citizen.id,
    workflow_state=state,
    votes=[],
    images=[],
  )


@pytest.mark.asyncio
async def test_local_storage_streams_supported_image(monkeypatch, tmp_path) -> None:
  monkeypatch.setattr(settings, "TICKET_MEDIA_ROOT", str(tmp_path))
  upload = UploadFile(
    file=BytesIO(b"jpeg-bytes"),
    filename="../damage.jpg",
    headers=Headers({"content-type": "image/jpeg"}),
  )

  stored = await LocalTicketMediaStorage.save_upload(
    upload,
    ticket_id=uuid4(),
    image_id=uuid4(),
  )

  assert stored.original_filename == "damage.jpg"
  assert stored.mime_type == "image/jpeg"
  assert stored.size_bytes == len(b"jpeg-bytes")
  assert (Path(tmp_path) / stored.storage_key).read_bytes() == b"jpeg-bytes"


@pytest.mark.asyncio
async def test_citizen_cannot_change_images_after_dispatch() -> None:
  citizen = _citizen()
  ticket = _ticket(citizen, TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT)

  with pytest.raises(ConflictException) as error:
    await TicketImageService._require_manage_permission(
      AsyncMock(),
      ticket,
      citizen,
    )

  assert error.value.error_code == "TICKET_ALREADY_IN_PROCESS"


@pytest.mark.asyncio
async def test_upload_records_image_event_and_projection(monkeypatch, tmp_path) -> None:
  from datetime import datetime, timezone

  from src.ticket.events import TicketEventType
  from src.ticket.media_storage import StoredTicketImage
  from src.ticket.models import TicketEvent, TicketImage

  citizen = _citizen()
  ticket = _ticket(citizen, TicketWorkflowState.NEW)
  db = AsyncMock()
  db.flush = AsyncMock()
  upload = object()
  event = TicketEvent(
    id=uuid4(),
    ticket_id=ticket.id,
    sequence_number=2,
    event_type=TicketEventType.TICKET_IMAGE_ADDED,
    actor_user_id=citizen.id,
    occurred_at=datetime.now(timezone.utc),
    payload={},
    citizen_visible=False,
  )
  staged: list[TicketImage] = []

  monkeypatch.setattr(settings, "TICKET_MEDIA_ROOT", str(tmp_path))
  monkeypatch.setattr(
    "src.ticket.services.images.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.services.images.TicketRepository.get_images",
    AsyncMock(return_value=[]),
  )
  monkeypatch.setattr(
    "src.ticket.services.images.LocalTicketMediaStorage.save_upload",
    AsyncMock(
      return_value=StoredTicketImage(
        storage_key=f"{ticket.id}/image.jpg",
        original_filename="image.jpg",
        mime_type="image/jpeg",
        size_bytes=100,
      )
    ),
  )
  append_event = AsyncMock(return_value=event)
  monkeypatch.setattr(
    "src.ticket.services.images.TicketEventStore._append_event",
    append_event,
  )
  monkeypatch.setattr(
    "src.ticket.services.images.TicketRepository.add_image",
    lambda _db, image: staged.append(image),
  )

  response = await TicketImageService.add_image(db, ticket.id, upload, citizen)

  assert response.is_cover is True
  assert response.is_active is True
  assert len(staged) == 1
  assert staged[0].added_event_id == event.id
  assert staged[0].storage_key.endswith("image.jpg")
  assert append_event.await_args.kwargs["event_type"] == TicketEventType.TICKET_IMAGE_ADDED
