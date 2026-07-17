from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import ForbiddenException
from src.ticket.events import (
  EscalationDecision,
  TicketCategory,
  TicketCompletionOutcome,
  TicketEventType,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketEvent
from src.ticket.schemas import (
  CompleteTicketAction,
  CosignTicketAction,
  DecideEscalationAction,
  RequestCosignatureAction,
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
    visibility=TicketVisibility.PUBLIC,
    public_status=TicketStatus.IN_PROGRESS,
    public_status_message="In progress",
    workflow_state=workflow_state,
    primary_officer_id=coordinator_id,
    current_responsible_user_id=coordinator_id,
    pending_return_to_user_id=pending_return_to_user_id,
    version=version,
    created_at=now,
    updated_at=now,
  )


def _mock_event_writes(monkeypatch, staged: list[TicketEvent]) -> None:
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.add_event",
    lambda _db, event: staged.append(event),
  )


@pytest.mark.asyncio
async def test_cosignature_is_sequential_and_returns_to_requester(monkeypatch) -> None:
  db = AsyncMock()
  requester = _user(Role.OFFICER, office_id=uuid4())
  cosigner = _user(Role.MANAGER, office_id=uuid4())
  ticket = _ticket(uuid4(), coordinator_id=requester.id)
  staged: list[TicketEvent] = []

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(side_effect=[cosigner, requester]),
  )
  _mock_event_writes(monkeypatch, staged)

  await TicketWorkflowCommandService.request_cosignature(
    db,
    ticket.id,
    RequestCosignatureAction(
      action=TicketWorkflowAction.REQUEST_COSIGNATURE,
      targetUserId=cosigner.id,
      comment="Please review",
    ),
    requester,
  )
  assert ticket.workflow_state == TicketWorkflowState.WAITING_FOR_COSIGNATURE
  assert ticket.current_responsible_user_id == cosigner.id

  await TicketWorkflowCommandService.cosign_ticket(
    db,
    ticket.id,
    CosignTicketAction(
      action=TicketWorkflowAction.COSIGN,
      comment="Cosigned",
    ),
    cosigner,
  )
  assert ticket.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert ticket.current_responsible_user_id == requester.id
  assert [event.event_type for event in staged] == [
    TicketEventType.COSIGNATURE_REQUESTED,
    TicketEventType.TICKET_COSIGNED,
  ]


@pytest.mark.asyncio
async def test_escalation_decision_is_one_command(monkeypatch) -> None:
  db = AsyncMock()
  requester = _user(Role.OFFICER)
  manager = _user(Role.MANAGER)
  ticket = _ticket(
    uuid4(),
    coordinator_id=manager.id,
    workflow_state=TicketWorkflowState.WAITING_FOR_DECISION,
    pending_return_to_user_id=requester.id,
    version=4,
  )
  staged: list[TicketEvent] = []

  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=requester),
  )
  _mock_event_writes(monkeypatch, staged)

  await TicketWorkflowCommandService.decide_escalation(
    db,
    ticket.id,
    DecideEscalationAction(
      action=TicketWorkflowAction.DECIDE_ESCALATION,
      decision=EscalationDecision.APPROVED,
      comment="Approved",
    ),
    manager,
  )

  assert ticket.current_responsible_user_id == requester.id
  assert ticket.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert staged[-1].event_type == TicketEventType.ESCALATION_DECIDED
  assert staged[-1].payload["decision"] == "APPROVED"


@pytest.mark.asyncio
async def test_only_manager_can_complete_as_rejected(monkeypatch) -> None:
  db = AsyncMock()
  officer = _user(Role.OFFICER)
  ticket = _ticket(uuid4(), coordinator_id=officer.id)
  monkeypatch.setattr(
    "src.ticket.repository.TicketRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )

  with pytest.raises(ForbiddenException):
    await TicketWorkflowCommandService.complete_ticket(
      db,
      ticket.id,
      CompleteTicketAction(
        action=TicketWorkflowAction.COMPLETE,
        outcome=TicketCompletionOutcome.REJECTED,
        message="Not responsible",
      ),
      officer,
    )
