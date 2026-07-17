from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.ticket.events import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowAction,
  TicketWorkflowState,
  TicketWorkItemOutcome,
  TicketWorkItemStatus,
)
from src.ticket.models import Ticket, TicketEvent, TicketWorkItem
from src.ticket.schemas import (
  CompleteWorkItemAction,
  PrimaryOfficerAssignmentRequest,
  RequestParallelCosignaturesAction,
  TicketDispatchRequest,
)
from src.ticket.workflow_service import TicketWorkflowService
from src.user.models import Role, User


def _user(role: Role, *, office_id: UUID | None = None) -> User:
  return User(
    id=uuid4(),
    email=f"{uuid4()}@example.com",
    hashed_password="hash",
    first_name="Test",
    last_name=role.value,
    role=role,
    office_id=office_id,
    is_active=True,
  )


def _ticket(
  creator_id: UUID,
  *,
  workflow_state: TicketWorkflowState,
  office_id: UUID | None = None,
  primary_officer_id: UUID | None = None,
  current_responsible_user_id: UUID | None = None,
  version: int = 1,
) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid4(),
    title="Pothole",
    description="Deep road damage",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=creator_id,
    office_id=office_id,
    visibility=TicketVisibility.PUBLIC,
    public_status=(
      TicketStatus.OPEN
      if workflow_state == TicketWorkflowState.NEW
      else TicketStatus.IN_PROGRESS
    ),
    public_status_message="Ticket submitted",
    workflow_state=workflow_state,
    primary_officer_id=primary_officer_id,
    current_responsible_user_id=current_responsible_user_id,
    version=version,
    created_at=now,
    updated_at=now,
  )


@pytest.mark.asyncio
async def test_dispatch_moves_ticket_to_active_office(monkeypatch) -> None:
  db = AsyncMock()
  dispatcher = _user(Role.DISPATCHER)
  office_id = uuid4()
  ticket = _ticket(uuid4(), workflow_state=TicketWorkflowState.NEW)
  staged_events: list[TicketEvent] = []
  sentinel = object()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.office.repository.OfficeRepository.get_by_id",
    AsyncMock(return_value=SimpleNamespace(id=office_id, is_active=True)),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, event: staged_events.append(event),
  )
  monkeypatch.setattr(
    TicketWorkflowService,
    "_internal_detail_response",
    AsyncMock(return_value=sentinel),
  )

  response = await TicketWorkflowService.dispatch_ticket(
    db,
    ticket.id,
    TicketDispatchRequest(officeId=office_id),
    dispatcher,
  )

  assert response is sentinel
  assert ticket.office_id == office_id
  assert ticket.workflow_state == TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
  assert ticket.public_status == TicketStatus.IN_PROGRESS
  assert staged_events[-1].event_type == TicketEventType.TICKET_DISPATCHED
  assert staged_events[-1].sequence_number == 2


@pytest.mark.asyncio
async def test_manager_assigns_officer_as_permanent_case_owner(monkeypatch) -> None:
  db = AsyncMock()
  office_id = uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  officer = _user(Role.OFFICER, office_id=office_id)
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    office_id=office_id,
    version=2,
  )
  sentinel = object()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=officer),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, _event: None,
  )
  monkeypatch.setattr(
    TicketWorkflowService,
    "_internal_detail_response",
    AsyncMock(return_value=sentinel),
  )

  await TicketWorkflowService.assign_primary_officer(
    db,
    ticket.id,
    PrimaryOfficerAssignmentRequest(primaryOfficerId=officer.id),
    manager,
  )

  assert ticket.primary_officer_id == officer.id
  assert ticket.current_responsible_user_id == officer.id
  assert ticket.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert ticket.version == 3


@pytest.mark.asyncio
async def test_parallel_cosignatures_create_independent_work_items(monkeypatch) -> None:
  db = AsyncMock()
  office_id = uuid4()
  coordinator = _user(Role.OFFICER, office_id=office_id)
  assignee_a = _user(Role.OFFICER, office_id=office_id)
  assignee_b = _user(Role.MANAGER, office_id=uuid4())
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    office_id=office_id,
    primary_officer_id=coordinator.id,
    current_responsible_user_id=coordinator.id,
    version=3,
  )
  staged_items: list[TicketWorkItem] = []
  users = {assignee_a.id: assignee_a, assignee_b.id: assignee_b}
  sentinel = object()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.has_open_blocking_work_items",
    AsyncMock(return_value=False),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(side_effect=lambda _db, user_id: users.get(user_id)),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, _event: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_work_item",
    lambda _db, item: staged_items.append(item),
  )
  monkeypatch.setattr(
    TicketWorkflowService,
    "_internal_detail_response",
    AsyncMock(return_value=sentinel),
  )

  await TicketWorkflowService.execute_workflow(
    db,
    ticket.id,
    RequestParallelCosignaturesAction(
      action=TicketWorkflowAction.REQUEST_PARALLEL_COSIGNATURES,
      assigneeUserIds=[assignee_a.id, assignee_b.id],
      comment="Please review in parallel",
    ),
    coordinator,
  )

  assert len(staged_items) == 2
  assert len({item.group_id for item in staged_items}) == 1
  assert {item.assignee_user_id for item in staged_items} == {
    assignee_a.id,
    assignee_b.id,
  }
  assert all(item.status == TicketWorkItemStatus.OPEN for item in staged_items)
  assert ticket.current_responsible_user_id == coordinator.id
  assert ticket.version == 4


@pytest.mark.asyncio
async def test_completing_one_work_item_does_not_close_its_siblings(monkeypatch) -> None:
  db = AsyncMock()
  coordinator = _user(Role.OFFICER, office_id=uuid4())
  assignee = _user(Role.MANAGER, office_id=uuid4())
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    office_id=coordinator.office_id,
    primary_officer_id=coordinator.id,
    current_responsible_user_id=coordinator.id,
    version=4,
  )
  item = TicketWorkItem(
    id=uuid4(),
    ticket_id=ticket.id,
    group_id=uuid4(),
    kind="COSIGNATURE",
    status=TicketWorkItemStatus.OPEN,
    assignee_user_id=assignee.id,
    requested_by_user_id=coordinator.id,
    return_to_user_id=coordinator.id,
    requested_event_id=uuid4(),
    is_blocking=True,
    created_at=datetime.now(timezone.utc),
  )
  sentinel = object()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_work_item_for_update",
    AsyncMock(return_value=item),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, _event: None,
  )
  monkeypatch.setattr(
    TicketWorkflowService,
    "_internal_detail_response",
    AsyncMock(return_value=sentinel),
  )

  await TicketWorkflowService.execute_workflow(
    db,
    ticket.id,
    CompleteWorkItemAction(
      action=TicketWorkflowAction.COMPLETE_WORK_ITEM,
      workItemId=item.id,
      outcome=TicketWorkItemOutcome.APPROVED,
      comment="No objections",
    ),
    assignee,
  )

  assert item.status == TicketWorkItemStatus.COMPLETED
  assert item.outcome == TicketWorkItemOutcome.APPROVED
  assert item.completed_event_id is not None
  assert item.completed_at is not None
  assert ticket.current_responsible_user_id == coordinator.id
  assert ticket.version == 5


@pytest.mark.asyncio
async def test_allowed_actions_separate_coordinator_and_task_permissions(monkeypatch) -> None:
  db = AsyncMock()
  coordinator = _user(Role.OFFICER, office_id=uuid4())
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    office_id=coordinator.office_id,
    primary_officer_id=coordinator.id,
    current_responsible_user_id=coordinator.id,
  )

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_open_work_item_ids_for_user",
    AsyncMock(return_value=[]),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.has_open_blocking_work_items",
    AsyncMock(return_value=False),
  )

  allowed = await TicketWorkflowService._allowed_actions(db, ticket, coordinator)

  assert allowed.actions == [TicketWorkflowAction.REQUEST_PARALLEL_COSIGNATURES]
  assert allowed.completable_work_item_ids == []
