from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import ConflictException
from src.media.storage import StoredImage
from src.ticket.domain import TicketCategory, TicketWorkflowState
from src.ticket.models import Ticket
from src.ticket.services.images import TicketImageService
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
    images=[],
  )


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
async def test_upload_records_validated_image_event_and_projection(
  monkeypatch,
) -> None:
  from datetime import datetime, timezone

  from src.ticket.domain import TicketEventType
  from src.ticket.models import TicketEvent, TicketImage

  citizen = _citizen()
  ticket = _ticket(citizen, TicketWorkflowState.NEW)
  db = AsyncMock()
  db.info = {}
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
  )
  staged: list[TicketImage] = []

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.repositories.image.TicketImageRepository.get_images",
    AsyncMock(return_value=[]),
  )
  monkeypatch.setattr(
    "src.ticket.services.images.LocalImageStorage.resolve_file",
    lambda *args, **kwargs: __import__("pathlib").Path("/tmp/ticket-image-test.jpg"),
  )
  monkeypatch.setattr(
    "src.ticket.services.images.LocalImageStorage.save_upload",
    AsyncMock(
      return_value=StoredImage(
        storage_key=f"{ticket.id}/image.jpg",
        original_filename="image.jpg",
        mime_type="image/jpeg",
        size_bytes=100,
        width=640,
        height=480,
      )
    ),
  )
  append_event = AsyncMock(return_value=event)
  monkeypatch.setattr(
    "src.ticket.services.images.TicketEventStore.append",
    append_event,
  )
  monkeypatch.setattr(
    "src.ticket.repositories.image.TicketImageRepository.add_image",
    lambda _db, image: staged.append(image),
  )

  response = await TicketImageService.add_image(db, ticket.id, upload, citizen)

  assert response.is_cover is True
  assert response.is_active is True
  assert (response.width, response.height) == (640, 480)
  assert "uploaded_by_user_id" not in response.model_dump()
  assert len(staged) == 1
  assert staged[0].added_event_id == event.id
  assert staged[0].storage_key.endswith("image.jpg")
  assert append_event.await_args.kwargs["event_type"] == TicketEventType.TICKET_IMAGE_ADDED
  payload = append_event.await_args.kwargs["payload"]
  assert (payload.width, payload.height) == (640, 480)
