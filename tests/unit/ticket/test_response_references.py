from datetime import datetime, timezone
from uuid import uuid4

from src.office.models import Office
from src.ticket.domain import TicketEventType
from src.ticket.models import TicketEvent
from src.ticket.services.mapper import TicketResponseMapper
from src.user.models import Role, User


def _user(*, office_id=None, first_name="Test", last_name="User") -> User:
  return User(
    id=uuid4(),
    email=f"{uuid4()}@example.com",
    hashed_password="hash",
    first_name=first_name,
    last_name=last_name,
    role=Role.OFFICER,
    office_id=office_id,
    is_active=True,
  )


def test_event_response_enriches_immutable_payload_without_changing_it() -> None:
  office = Office(id=uuid4(), name="Building Office", is_active=True)
  actor = _user(office_id=office.id, first_name="Alex", last_name="Actor")
  target = _user(office_id=office.id, first_name="Taylor", last_name="Target")
  payload = {
    "target_user_id": str(target.id),
    "office_id": str(office.id),
    "comment": "Please continue",
  }
  event = TicketEvent(
    id=uuid4(),
    ticket_id=uuid4(),
    sequence_number=5,
    event_type=TicketEventType.TICKET_FORWARDED,
    actor_user_id=actor.id,
    occurred_at=datetime.now(timezone.utc),
    payload=payload.copy(),
  )
  event.actor = actor

  response = TicketResponseMapper.to_event(
    event,
    users={str(target.id): target},
    offices={str(office.id): office},
  )

  assert response.actor.id == actor.id
  assert response.actor.display_name == "Alex Actor"
  assert [reference.id for reference in response.references.users] == [target.id]
  assert [reference.id for reference in response.references.offices] == [office.id]
  assert response.payload == payload
  assert event.payload == payload
