"""Pure replay helpers for the revisioned ticket-image projection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.ticket.domain.enums import TicketEventType
from src.ticket.domain.payloads import (
  TicketCoverImageChangedPayload,
  TicketImageAddedPayload,
  TicketImageRemovedPayload,
  validate_event_payload,
)


class TicketImageProjectionState(BaseModel):
  """Image metadata reconstructed exclusively from ticket events."""

  id: UUID
  storage_key: str
  original_filename: str
  mime_type: str
  size_bytes: int
  uploaded_by_user_id: UUID
  uploaded_at: datetime
  is_active: bool
  is_cover: bool
  removed_at: datetime | None = None
  removed_by_user_id: UUID | None = None
  added_event_id: UUID
  removed_event_id: UUID | None = None
  cover_selected_event_id: UUID | None = None


def rebuild_ticket_images(
  events: list[tuple[UUID, TicketEventType, UUID, dict, datetime]],
) -> dict[UUID, TicketImageProjectionState]:
  """Rebuild all current and removed image projections from ordered events."""

  images: dict[UUID, TicketImageProjectionState] = {}
  for event_id, event_type, actor_user_id, raw_payload, occurred_at in events:
    if event_type == TicketEventType.TICKET_IMAGE_ADDED:
      payload = validate_event_payload(event_type, raw_payload)
      assert isinstance(payload, TicketImageAddedPayload)
      images[payload.image_id] = TicketImageProjectionState(
        id=payload.image_id,
        storage_key=payload.storage_key,
        original_filename=payload.original_filename,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        uploaded_by_user_id=actor_user_id,
        uploaded_at=occurred_at,
        is_active=True,
        is_cover=payload.is_cover,
        added_event_id=event_id,
        cover_selected_event_id=(event_id if payload.is_cover else None),
      )
    elif event_type == TicketEventType.TICKET_IMAGE_REMOVED:
      payload = validate_event_payload(event_type, raw_payload)
      assert isinstance(payload, TicketImageRemovedPayload)
      image = images.get(payload.image_id)
      if image is None:
        raise ValueError("Image removal references an unknown ticket image")
      image.is_active = False
      image.is_cover = False
      image.removed_at = occurred_at
      image.removed_by_user_id = actor_user_id
      image.removed_event_id = event_id
    elif event_type == TicketEventType.TICKET_COVER_IMAGE_CHANGED:
      payload = validate_event_payload(event_type, raw_payload)
      assert isinstance(payload, TicketCoverImageChangedPayload)
      selected = images.get(payload.image_id)
      if selected is None or not selected.is_active:
        raise ValueError("Cover selection references an unavailable ticket image")
      for image in images.values():
        if image.is_active:
          image.is_cover = image.id == selected.id
      selected.cover_selected_event_id = event_id
  return images
