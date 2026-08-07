"""Extend ticket assignment and dispatch events.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-19
"""

from collections.abc import Sequence

from alembic import op


revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_EVENT_TYPES = (
  "TICKET_SUBMITTED",
  "TICKET_DETAILS_UPDATED",
  "TICKET_CANCELLED",
  "TICKET_DISPATCHED",
  "PRIMARY_OFFICER_ASSIGNED",
  "PRIMARY_OFFICER_REASSIGNED",
  "TICKET_RETURNED_TO_DISPATCH",
  "TICKET_FORWARDED",
  "COSIGNATURE_REQUESTED",
  "TICKET_COSIGNED",
  "CITIZEN_RESPONSE_REQUESTED",
  "CITIZEN_RESPONDED",
  "TICKET_ESCALATED",
  "ESCALATION_DECIDED",
  "TICKET_COMPLETED",
  "TICKET_COMMENTED",
  "TICKET_IMAGE_ADDED",
  "TICKET_IMAGE_REMOVED",
  "TICKET_COVER_IMAGE_CHANGED",
)

_OLD_EVENT_TYPES = tuple(
  event_type
  for event_type in _EVENT_TYPES
  if event_type not in {
    "PRIMARY_OFFICER_REASSIGNED",
    "TICKET_RETURNED_TO_DISPATCH",
  }
)


def _check(values: tuple[str, ...]) -> str:
  return "event_type IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Allow ownership replacement and return-to-dispatch events."""

  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    _check(_EVENT_TYPES),
  )


def downgrade() -> None:
  """Restore the former event set when no new assignment events exist."""

  op.execute(
    "DO $$ BEGIN "
    "IF EXISTS (SELECT 1 FROM ticket_events WHERE event_type IN ("
    "'PRIMARY_OFFICER_REASSIGNED', 'TICKET_RETURNED_TO_DISPATCH')) THEN "
    "RAISE EXCEPTION 'Cannot downgrade tickets containing new assignment events'; "
    "END IF; END $$"
  )
  op.drop_constraint("ck_ticket_events_event_type", "ticket_events", type_="check")
  op.create_check_constraint(
    "ck_ticket_events_event_type",
    "ticket_events",
    _check(_OLD_EVENT_TYPES),
  )
