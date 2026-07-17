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
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import PrimaryOfficerAssignmentRequest, TicketDispatchRequest
from src.ticket.services.workflow.queries import TicketWorkflowQueryService
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
  pending_return_to_user_id: UUID | None = None,
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
    current_responsible_user_id=current_responsible_user_id,
    pending_return_to_user_id=pending_return_to_user_id,
    version=version,
    created_at=now,
    updated_at=now,
  )


def _mock_writes(monkeypatch, events: list[TicketEvent]) -> None:
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, event: events.append(event),
  )


@pytest.mark.asyncio
async def test_dispatch_moves_ticket_to_active_office(monkeypatch) -> None:
  db = AsyncMock()
  dispatcher = _user(Role.DISPATCHER)
  office_id = uuid4()
  ticket = _ticket(uuid4(), workflow_state=TicketWorkflowState.NEW)
  staged: list[TicketEvent] = []
  sentinel = object()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.office.repository.OfficeRepository.get_by_id",
    AsyncMock(return_value=SimpleNamespace(id=office_id, is_active=True)),
  )
  _mock_writes(monkeypatch, staged)
  monkeypatch.setattr(
    TicketWorkflowQueryService,
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
  sentinel = object()

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=officer),
  )
  _mock_writes(monkeypatch, [])
  monkeypatch.setattr(
    TicketWorkflowQueryService,
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


def test_allowed_actions_expose_sequential_ad_hoc_steps() -> None:
  officer = _user(Role.OFFICER)
  ticket = _ticket(
    uuid4(),
    workflow_state=TicketWorkflowState.IN_PROGRESS,
    primary_officer_id=officer.id,
    current_responsible_user_id=officer.id,
  )
  assert TicketWorkflowQueryService._allowed_actions(ticket, officer) == [
    TicketWorkflowAction.FORWARD,
    TicketWorkflowAction.REQUEST_COSIGNATURE,
    TicketWorkflowAction.ESCALATE,
    TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
    TicketWorkflowAction.COMPLETE,
  ]
