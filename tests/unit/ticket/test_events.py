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


def test_escalation_and_decision_preserve_primary_officer() -> None:
  from src.ticket.events import EscalationDecisionPayload, TicketEscalatedPayload

  now = datetime.now(timezone.utc)
  primary_id = uuid4()
  manager_id = uuid4()
  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Damaged sidewalk",
      category=TicketCategory.INFRASTRUCTURE,
      creator_user_id=uuid4(),
    ),
    occurred_at=now,
  )
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_DISPATCHED,
    TicketDispatchedPayload(office_id=uuid4()),
    occurred_at=now + timedelta(minutes=1),
  )
  state = evolve_ticket(
    state,
    TicketEventType.PRIMARY_OFFICER_ASSIGNED,
    PrimaryOfficerAssignedPayload(primary_officer_id=primary_id),
    occurred_at=now + timedelta(minutes=2),
  )

  state = evolve_ticket(
    state,
    TicketEventType.TICKET_ESCALATED,
    TicketEscalatedPayload(
      manager_user_id=manager_id,
      return_to_user_id=primary_id,
      reason="Approval required",
    ),
    occurred_at=now + timedelta(minutes=3),
  )

  assert state.primary_officer_id == primary_id
  assert state.current_responsible_user_id == manager_id
  assert state.pending_return_to_user_id == primary_id
  assert state.workflow_state == TicketWorkflowState.WAITING_FOR_APPROVAL

  state = evolve_ticket(
    state,
    TicketEventType.ESCALATION_APPROVED,
    EscalationDecisionPayload(return_to_user_id=primary_id, comment="Approved"),
    occurred_at=now + timedelta(minutes=4),
  )

  assert state.primary_officer_id == primary_id
  assert state.current_responsible_user_id == primary_id
  assert state.pending_return_to_user_id is None
  assert state.workflow_state == TicketWorkflowState.IN_PROGRESS


def test_citizen_response_round_trip_uses_pending_return_target() -> None:
  from src.ticket.events import CitizenRespondedPayload, CitizenResponseRequestedPayload

  now = datetime.now(timezone.utc)
  creator_id = uuid4()
  officer_id = uuid4()
  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Street damage",
      category=TicketCategory.INFRASTRUCTURE,
      creator_user_id=creator_id,
    ),
    occurred_at=now,
  )
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_DISPATCHED,
    TicketDispatchedPayload(office_id=uuid4()),
    occurred_at=now + timedelta(minutes=1),
  )
  state = evolve_ticket(
    state,
    TicketEventType.PRIMARY_OFFICER_ASSIGNED,
    PrimaryOfficerAssignedPayload(primary_officer_id=officer_id),
    occurred_at=now + timedelta(minutes=2),
  )
  state = evolve_ticket(
    state,
    TicketEventType.CITIZEN_RESPONSE_REQUESTED,
    CitizenResponseRequestedPayload(
      question="Which house number is affected?",
      return_to_user_id=officer_id,
    ),
    occurred_at=now + timedelta(minutes=3),
  )

  assert state.current_responsible_user_id == creator_id
  assert state.pending_return_to_user_id == officer_id
  assert state.workflow_state == TicketWorkflowState.WAITING_FOR_CITIZEN
  assert state.public_status_message == "Which house number is affected?"

  state = evolve_ticket(
    state,
    TicketEventType.CITIZEN_RESPONDED,
    CitizenRespondedPayload(
      message="House number 12",
      return_to_user_id=officer_id,
    ),
    occurred_at=now + timedelta(minutes=4),
  )

  assert state.current_responsible_user_id == officer_id
  assert state.pending_return_to_user_id is None
  assert state.workflow_state == TicketWorkflowState.IN_PROGRESS


def test_image_events_are_part_of_the_aggregate_sequence() -> None:
  from src.ticket.events import (
    TicketCoverImageChangedPayload,
    TicketImageAddedPayload,
    TicketImageRemovedPayload,
  )

  now = datetime.now(timezone.utc)
  image_id = uuid4()
  state = evolve_ticket(
    None,
    TicketEventType.TICKET_SUBMITTED,
    TicketSubmittedPayload(
      title="Broken pavement",
      category=TicketCategory.INFRASTRUCTURE,
      creator_user_id=uuid4(),
    ),
    occurred_at=now,
  )
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_IMAGE_ADDED,
    TicketImageAddedPayload(
      image_id=image_id,
      storage_key=f"ticket/{image_id}.jpg",
      original_filename="damage.jpg",
      mime_type="image/jpeg",
      size_bytes=123,
      is_cover=True,
    ),
    occurred_at=now + timedelta(seconds=1),
  )
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_COVER_IMAGE_CHANGED,
    TicketCoverImageChangedPayload(image_id=image_id),
    occurred_at=now + timedelta(seconds=2),
  )
  state = evolve_ticket(
    state,
    TicketEventType.TICKET_IMAGE_REMOVED,
    TicketImageRemovedPayload(image_id=image_id, reason="Blurred image"),
    occurred_at=now + timedelta(seconds=3),
  )

  assert state.version == 4
  assert state.title == "Broken pavement"
  assert state.workflow_state == TicketWorkflowState.NEW
