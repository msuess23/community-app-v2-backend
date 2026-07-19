from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.ticket.domain import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import PrimaryOfficerAssignmentRequest, TicketDispatchRequest
from src.ticket.services.workflow_commands import TicketWorkflowCommandService
from src.ticket.services.workflow_queries import TicketWorkflowQueryService
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
  current_assignee_id: UUID | None = None,
  return_to_user_id: UUID | None = None,
  version: int = 1,
) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid4(),
    title="Pothole",
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
    current_assignee_id=current_assignee_id,
    return_to_user_id=return_to_user_id,
    version=version,
    created_at=now,
    updated_at=now,
  )


def _mock_writes(monkeypatch, events: list[TicketEvent]) -> None:
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repositories.event.TicketEventRepository.add_event",
    lambda _db, event: events.append(event),
  )


@pytest.mark.asyncio
async def test_dispatch_moves_ticket_to_active_office(monkeypatch) -> None:
  db = AsyncMock()
  dispatcher = _user(Role.DISPATCHER)
  office_id = uuid4()
  ticket = _ticket(uuid4(), workflow_state=TicketWorkflowState.NEW)
  staged: list[TicketEvent] = []

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.office.repository.OfficeRepository.get_by_id",
    AsyncMock(return_value=SimpleNamespace(id=office_id, is_active=True)),
  )
  _mock_writes(monkeypatch, staged)

  response = await TicketWorkflowCommandService.dispatch_ticket(
    db,
    ticket.id,
    TicketDispatchRequest(office_id=office_id),
    dispatcher,
  )
  assert response is ticket
  assert ticket.office_id == office_id
  assert staged[-1].event_type == TicketEventType.TICKET_DISPATCHED


@pytest.mark.asyncio
async def test_manager_assigns_permanent_officer(monkeypatch) -> None:
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

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=officer),
  )
  _mock_writes(monkeypatch, [])

  response = await TicketWorkflowCommandService.assign_primary_officer(
    db,
    ticket.id,
    PrimaryOfficerAssignmentRequest(primary_officer_id=officer.id),
    manager,
  )
  assert response is ticket
  assert ticket.primary_officer_id == officer.id
  assert ticket.current_assignee_id == officer.id


def test_allowed_actions_expose_sequential_ad_hoc_steps() -> None:
  officer = _user(Role.OFFICER)
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    primary_officer_id=officer.id,
    current_assignee_id=officer.id,
  )
  assert TicketWorkflowQueryService._allowed_actions(ticket, officer) == [
    TicketWorkflowAction.FORWARD,
    TicketWorkflowAction.REQUEST_COSIGNATURE,
    TicketWorkflowAction.ESCALATE,
    TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
    TicketWorkflowAction.RETURN_TO_DISPATCH,
    TicketWorkflowAction.COMPLETE,
  ]


@pytest.mark.asyncio
async def test_manager_can_replace_primary_officer(monkeypatch) -> None:
  db = AsyncMock()
  office_id = uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  previous = _user(Role.OFFICER, office_id=office_id)
  replacement = _user(Role.OFFICER, office_id=office_id)
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    office_id=office_id,
    primary_officer_id=previous.id,
    current_assignee_id=previous.id,
    version=3,
  )
  staged: list[TicketEvent] = []

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=replacement),
  )
  _mock_writes(monkeypatch, staged)

  await TicketWorkflowCommandService.assign_primary_officer(
    db,
    ticket.id,
    PrimaryOfficerAssignmentRequest(primary_officer_id=replacement.id),
    manager,
  )

  assert ticket.primary_officer_id == replacement.id
  assert ticket.current_assignee_id == replacement.id
  assert staged[-1].event_type == TicketEventType.PRIMARY_OFFICER_REASSIGNED
  assert staged[-1].payload["previous_primary_officer_id"] == str(previous.id)


@pytest.mark.asyncio
async def test_internal_archive_forwards_extended_filters(monkeypatch) -> None:
  from src.ticket.domain import TicketLifecycleFilter
  from src.ticket.repositories.ticket import TicketProjectionRepository

  manager = _user(Role.MANAGER, office_id=uuid4())
  creator_id = uuid4()
  primary_id = uuid4()
  assignee_id = uuid4()
  repository_call = AsyncMock(return_value=([], 0))
  monkeypatch.setattr(TicketProjectionRepository, "get_staff_page", repository_call)
  monkeypatch.setattr(
    "src.ticket.repositories.event.TicketEventRepository.get_events_for_tickets",
    AsyncMock(return_value=[]),
  )

  response = await TicketWorkflowQueryService.list_internal_tickets(
    AsyncMock(),
    current_user=manager,
    page=2,
    size=25,
    lifecycle=TicketLifecycleFilter.COMPLETED,
    office_id=manager.office_id,
    creator_user_id=creator_id,
    primary_officer_id=primary_id,
    current_assignee_id=assignee_id,
  )

  assert response.total == 0
  repository_call.assert_awaited_once()
  kwargs = repository_call.await_args.kwargs
  assert kwargs["lifecycle"] == TicketLifecycleFilter.COMPLETED
  assert kwargs["office_id"] == manager.office_id
  assert kwargs["creator_user_id"] == creator_id
  assert kwargs["primary_officer_id"] == primary_id
  assert kwargs["current_assignee_id"] == assignee_id
