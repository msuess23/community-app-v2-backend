from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.ticket.domain.image_projection import rebuild_ticket_images
from src.ticket.domain import TicketEventType


def test_image_projection_rebuilds_cover_and_removed_revisions() -> None:
  now = datetime.now(timezone.utc)
  actor = uuid4()
  first = uuid4()
  second = uuid4()
  add_first = uuid4()
  add_second = uuid4()
  cover_event = uuid4()
  remove_event = uuid4()

  projection = rebuild_ticket_images(
    [
      (
        add_first,
        TicketEventType.TICKET_IMAGE_ADDED,
        actor,
        {
          "image_id": str(first),
          "storage_key": "ticket/first.jpg",
          "original_filename": "first.jpg",
          "mime_type": "image/jpeg",
          "size_bytes": 100,
          "is_cover": True,
        },
        now,
      ),
      (
        add_second,
        TicketEventType.TICKET_IMAGE_ADDED,
        actor,
        {
          "image_id": str(second),
          "storage_key": "ticket/second.jpg",
          "original_filename": "second.jpg",
          "mime_type": "image/jpeg",
          "size_bytes": 120,
          "is_cover": False,
        },
        now + timedelta(seconds=1),
      ),
      (
        cover_event,
        TicketEventType.TICKET_COVER_IMAGE_CHANGED,
        actor,
        {"image_id": str(second)},
        now + timedelta(seconds=2),
      ),
      (
        remove_event,
        TicketEventType.TICKET_IMAGE_REMOVED,
        actor,
        {"image_id": str(first), "reason": "Duplicate"},
        now + timedelta(seconds=3),
      ),
    ]
  )

  assert projection[first].is_active is False
  assert projection[first].removed_event_id == remove_event
  assert projection[second].is_cover is True
  assert projection[second].cover_selected_event_id == cover_event
