from src.appointment.models import Appointment, AppointmentEvent
from src.ticket.models import Ticket, TicketEvent


def _ondelete(model, column_name: str) -> str | None:
  """Return the single foreign key deletion rule for a mapped column."""

  foreign_keys = list(model.__table__.c[column_name].foreign_keys)
  assert len(foreign_keys) == 1
  return foreign_keys[0].ondelete


def test_aggregate_event_streams_cannot_be_cascade_deleted() -> None:
  """Protect ticket and appointment events independently of ORM usage."""

  assert _ondelete(TicketEvent, "ticket_id") == "RESTRICT"
  assert _ondelete(AppointmentEvent, "appointment_id") == "RESTRICT"
  assert "delete-orphan" not in str(Ticket.events.property.cascade)
  assert "delete-orphan" not in str(Appointment.events.property.cascade)
