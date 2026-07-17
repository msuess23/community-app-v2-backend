from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ticket.events import (
  ParallelWorkItemRequest,
  ParallelWorkItemsRequestedPayload,
  PrimaryOfficerAssignedPayload,
  TicketCategory,
  TicketDetailsUpdatedPayload,
  TicketDispatchedPayload,
  TicketEventType,
  TicketStatus,
  TicketSubmittedPayload,
  TicketVisibility,
  TicketWorkflowState,
  TicketWorkItemKind,
  evolve_ticket,
  rebuild_ticket,
)


def test_submission_starts_in_central_inbox_without_office() -> None:
  now = datetime.now(timezone.utc)
  creator_id = uuid4()

  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Pothole in Main Street",
      category=TicketCategory.INFRASTRUCTURE,
      creator_user_id=creator_id,
      visibility=TicketVisibility.PUBLIC,
    ),
    occurred_at=now,
  )

  assert state.creator_user_id == creator_id
  assert state.office_id is None
  assert state.primary_officer_id is None
  assert state.current_responsible_user_id is None
  assert state.workflow_state == TicketWorkflowState.NEW
  assert state.public_status == TicketStatus.OPEN
  assert state.version == 1


def test_dispatch_and_primary_assignment_keep_distinct_responsibilities() -> None:
  now = datetime.now(timezone.utc)
  office_id = uuid4()
  officer_id = uuid4()
  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Broken street light",
      category=TicketCategory.SAFETY,
      creator_user_id=uuid4(),
    ),
    occurred_at=now,
  )

  state = evolve_ticket(
    state,
    TicketEventType.TICKET_DISPATCHED,
    TicketDispatchedPayload(office_id=office_id),
    occurred_at=now + timedelta(minutes=1),
  )
  assert state.office_id == office_id
  assert state.workflow_state == TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
  assert state.primary_officer_id is None

  state = evolve_ticket(
    state,
    TicketEventType.PRIMARY_OFFICER_ASSIGNED,
    PrimaryOfficerAssignedPayload(primary_officer_id=officer_id),
    occurred_at=now + timedelta(minutes=2),
  )
  assert state.primary_officer_id == officer_id
  assert state.current_responsible_user_id == officer_id
  assert state.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert state.version == 3


def test_parallel_work_items_reject_duplicate_assignees() -> None:
  assignee = uuid4()

  with pytest.raises(ValidationError):
    ParallelWorkItemsRequestedPayload(
      group_id=uuid4(),
      return_to_user_id=uuid4(),
      items=[
        ParallelWorkItemRequest(
          assignee_user_id=assignee,
          kind=TicketWorkItemKind.COSIGNATURE,
        ),
        ParallelWorkItemRequest(
          assignee_user_id=assignee,
          kind=TicketWorkItemKind.CONSULTATION,
        ),
      ],
    )


def test_rebuild_ticket_applies_ordered_citizen_events() -> None:
  now = datetime.now(timezone.utc)
  events = [
    (
      TicketEventType.TICKET_SUBMITTED,
      TicketSubmittedPayload(
        title="Noise at night",
        description="Music after midnight",
        category=TicketCategory.NOISE,
        creator_user_id=uuid4(),
      ).model_dump(mode="json"),
      now,
    ),
    (
      TicketEventType.TICKET_DETAILS_UPDATED,
      TicketDetailsUpdatedPayload(
        description="Music after 1 AM",
        visibility=TicketVisibility.PRIVATE,
      ).model_dump(mode="json", exclude_unset=True),
      now + timedelta(minutes=1),
    ),
  ]

  state = rebuild_ticket(events)

  assert state.description == "Music after 1 AM"
  assert state.visibility == TicketVisibility.PRIVATE
  assert state.version == 2
