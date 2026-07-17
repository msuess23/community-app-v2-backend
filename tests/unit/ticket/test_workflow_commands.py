from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import ForbiddenException
from src.ticket.events import (
  TicketCategory,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import (
  ApproveEscalationAction,
  EscalateTicketAction,
  ForwardTicketAction,
  RejectTicketAction,
  RequestCitizenResponseAction,
  ResolveTicketAction,
  TicketCitizenResponseRequest,
)
from src.ticket.workflow_command_service import TicketWorkflowCommandService
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
  coordinator_id: UUID,
  primary_officer_id: UUID | None = None,
  workflow_state: TicketWorkflowState = TicketWorkflowState.IN_PROGRESS,
  pending_return_to_user_id: UUID | None = None,
  version: int = 3,
) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid4(),
    title="Pothole",
    description="Deep road damage",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=creator_id,
    office_id=uuid4(),
    visibility=TicketVisibility.PUBLIC,
    public_status=TicketStatus.IN_PROGRESS,
    public_status_message="In progress",
    workflow_state=workflow_state,
    primary_officer_id=primary_officer_id,
    current_responsible_user_id=coordinator_id,
    pending_return_to_user_id=pending_return_to_user_id,
    version=version,
    created_at=now,
    updated_at=now,
  )


def _mock_event_writes(monkeypatch, events: list[TicketEvent]) -> None:
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, event: events.append(event),
  )


@pytest.mark.asyncio
async def test_forward_changes_current_responsible_but_not_primary(monkeypatch) -> None:
  db = AsyncMock()
  primary = _user(Role.OFFICER, office_id=uuid4())
  target = _user(Role.MANAGER, office_id=uuid4())
  ticket = _ticket(
    uuid4(),
    coordinator_id=primary.id,
    primary_officer_id=primary.id,
  )
  events: list[TicketEvent] = []

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
    AsyncMock(return_value=target),
  )
  _mock_event_writes(monkeypatch, events)

  await TicketWorkflowCommandService.forward_ticket(
    db,
    ticket.id,
    ForwardTicketAction(
      action=TicketWorkflowAction.FORWARD,
      targetUserId=target.id,
      comment="Please continue processing",
    ),
    primary,
  )

  assert ticket.primary_officer_id == primary.id
  assert ticket.current_responsible_user_id == target.id
  assert events[-1].event_type == TicketEventType.TICKET_FORWARDED


@pytest.mark.asyncio
async def test_escalation_and_approval_return_to_requester(monkeypatch) -> None:
  db = AsyncMock()
  officer = _user(Role.OFFICER, office_id=uuid4())
  manager = _user(Role.MANAGER, office_id=uuid4())
  ticket = _ticket(
    uuid4(),
    coordinator_id=officer.id,
    primary_officer_id=officer.id,
  )
  events: list[TicketEvent] = []

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
    AsyncMock(side_effect=[manager, officer]),
  )
  _mock_event_writes(monkeypatch, events)

  await TicketWorkflowCommandService.escalate_ticket(
    db,
    ticket.id,
    EscalateTicketAction(
      action=TicketWorkflowAction.ESCALATE,
      managerUserId=manager.id,
      reason="Repair costs exceed the officer's authority",
    ),
    officer,
  )

  assert ticket.workflow_state == TicketWorkflowState.WAITING_FOR_APPROVAL
  assert ticket.current_responsible_user_id == manager.id
  assert ticket.pending_return_to_user_id == officer.id

  await TicketWorkflowCommandService.approve_escalation(
    db,
    ticket.id,
    ApproveEscalationAction(
      action=TicketWorkflowAction.APPROVE_ESCALATION,
      comment="Budget approved",
    ),
    manager,
  )

  assert ticket.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert ticket.current_responsible_user_id == officer.id
  assert ticket.pending_return_to_user_id is None
  assert events[-1].event_type == TicketEventType.ESCALATION_APPROVED
  assert events[-1].citizen_visible is True


@pytest.mark.asyncio
async def test_citizen_response_returns_case_to_requesting_officer(monkeypatch) -> None:
  db = AsyncMock()
  citizen = _user(Role.CITIZEN)
  officer = _user(Role.OFFICER, office_id=uuid4())
  ticket = _ticket(
    citizen.id,
    coordinator_id=officer.id,
    primary_officer_id=officer.id,
  )
  events: list[TicketEvent] = []

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
    AsyncMock(return_value=officer),
  )
  _mock_event_writes(monkeypatch, events)

  await TicketWorkflowCommandService.request_citizen_response(
    db,
    ticket.id,
    RequestCitizenResponseAction(
      action=TicketWorkflowAction.REQUEST_CITIZEN_RESPONSE,
      question="Which house number is affected?",
    ),
    officer,
  )

  assert ticket.workflow_state == TicketWorkflowState.WAITING_FOR_CITIZEN
  assert ticket.current_responsible_user_id == citizen.id
  assert ticket.pending_return_to_user_id == officer.id

  _, response_event = await TicketWorkflowCommandService.respond_as_citizen(
    db,
    ticket.id,
    TicketCitizenResponseRequest(message="House number 12"),
    citizen,
  )

  assert ticket.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert ticket.current_responsible_user_id == officer.id
  assert ticket.pending_return_to_user_id is None
  assert response_event.event_type == TicketEventType.CITIZEN_RESPONDED


@pytest.mark.asyncio
async def test_officer_can_resolve_but_cannot_reject_ticket(monkeypatch) -> None:
  db = AsyncMock()
  officer = _user(Role.OFFICER, office_id=uuid4())
  ticket = _ticket(
    uuid4(),
    coordinator_id=officer.id,
    primary_officer_id=officer.id,
  )
  events: list[TicketEvent] = []

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.has_open_work_items",
    AsyncMock(return_value=False),
  )
  _mock_event_writes(monkeypatch, events)

  await TicketWorkflowCommandService.resolve_ticket(
    db,
    ticket.id,
    ResolveTicketAction(
      action=TicketWorkflowAction.RESOLVE,
      message="Road surface repaired",
    ),
    officer,
  )

  assert ticket.workflow_state == TicketWorkflowState.COMPLETED
  assert ticket.public_status == TicketStatus.RESOLVED

  another_ticket = _ticket(
    uuid4(),
    coordinator_id=officer.id,
    primary_officer_id=officer.id,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=another_ticket),
  )

  with pytest.raises(ForbiddenException):
    await TicketWorkflowCommandService.reject_ticket(
      db,
      another_ticket.id,
      RejectTicketAction(
        action=TicketWorkflowAction.REJECT_TICKET,
        message="Not an authority responsibility",
      ),
      officer,
    )
