from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.exceptions import ForbiddenException
from src.ticket.services.errors import (
  TicketActionNotAllowedException,
  TicketCompletionOutcomeNotAllowedException,
  TicketTargetAlreadySelectedException,
  TicketTargetUnavailableException,
)
from src.ticket.domain import (
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
  ForwardTicketAction,
  PrimaryOfficerAssignmentRequest,
  DecideEscalationAction,
  RequestCosignatureAction,
)
from src.ticket.services.workflow_commands import TicketWorkflowCommandService
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
  return_to_user_id: UUID | None = None,
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
    current_assignee_id=coordinator_id,
    return_to_user_id=return_to_user_id,
    version=version,
    created_at=now,
    updated_at=now,
  )


def _mock_event_writes(monkeypatch, staged: list[TicketEvent], ticket: Ticket) -> None:
  monkeypatch.setattr(
    "src.ticket.repositories.event.TicketEventRepository.get_last_sequence_number",
    AsyncMock(side_effect=lambda *_args: ticket.version),
  )
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.add",
    lambda _db, _ticket: None,
  )
  monkeypatch.setattr(
    "src.ticket.repositories.event.TicketEventRepository.add_event",
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
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(side_effect=[cosigner, requester]),
  )
  _mock_event_writes(monkeypatch, staged, ticket)

  await TicketWorkflowCommandService.request_cosignature(
    db,
    ticket.id,
    RequestCosignatureAction(
      action=TicketWorkflowAction.REQUEST_COSIGNATURE,
      target_user_id=cosigner.id,
      comment="Please review",
    ),
    requester,
  )
  assert ticket.workflow_state == TicketWorkflowState.WAITING_FOR_COSIGNATURE
  assert ticket.current_assignee_id == cosigner.id

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
  assert ticket.current_assignee_id == requester.id
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
    return_to_user_id=requester.id,
    version=4,
  )
  staged: list[TicketEvent] = []

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=requester),
  )
  _mock_event_writes(monkeypatch, staged, ticket)

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

  assert ticket.current_assignee_id == requester.id
  assert ticket.workflow_state == TicketWorkflowState.IN_PROGRESS
  assert staged[-1].event_type == TicketEventType.ESCALATION_DECIDED
  assert staged[-1].payload["decision"] == "APPROVED"


@pytest.mark.asyncio
async def test_only_manager_can_complete_as_rejected(monkeypatch) -> None:
  db = AsyncMock()
  officer = _user(Role.OFFICER)
  ticket = _ticket(uuid4(), coordinator_id=officer.id)
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )

  with pytest.raises(TicketCompletionOutcomeNotAllowedException) as exc_info:
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
  assert exc_info.value.error_code == "TICKET_COMPLETION_OUTCOME_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_stale_workflow_action_has_stable_conflict_code(monkeypatch) -> None:
  officer = _user(Role.OFFICER)
  ticket = _ticket(
    uuid4(),
    coordinator_id=officer.id,
    workflow_state=TicketWorkflowState.WAITING_FOR_CITIZEN,
  )
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )

  with pytest.raises(TicketActionNotAllowedException) as exc_info:
    await TicketWorkflowCommandService.forward_ticket(
      AsyncMock(),
      ticket.id,
      ForwardTicketAction(
        action=TicketWorkflowAction.FORWARD,
        target_user_id=uuid4(),
      ),
      officer,
    )

  assert exc_info.value.error_code == "TICKET_ACTION_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_inactive_workflow_target_has_stable_conflict_code(monkeypatch) -> None:
  officer = _user(Role.OFFICER)
  inactive_target = _user(Role.OFFICER)
  inactive_target.is_active = False
  ticket = _ticket(uuid4(), coordinator_id=officer.id)
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=inactive_target),
  )

  with pytest.raises(TicketTargetUnavailableException) as exc_info:
    await TicketWorkflowCommandService.forward_ticket(
      AsyncMock(),
      ticket.id,
      ForwardTicketAction(
        action=TicketWorkflowAction.FORWARD,
        target_user_id=inactive_target.id,
      ),
      officer,
    )

  assert exc_info.value.error_code == "TICKET_TARGET_NO_LONGER_AVAILABLE"


@pytest.mark.asyncio
async def test_primary_reassignment_rejects_current_owner_as_no_op(monkeypatch) -> None:
  office_id = uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  officer = _user(Role.OFFICER, office_id=office_id)
  ticket = _ticket(uuid4(), coordinator_id=officer.id)
  ticket.office_id = office_id
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_by_id",
    AsyncMock(return_value=officer),
  )

  with pytest.raises(TicketTargetAlreadySelectedException) as exc_info:
    await TicketWorkflowCommandService.assign_primary_officer(
      AsyncMock(),
      ticket.id,
      PrimaryOfficerAssignmentRequest(primary_officer_id=officer.id),
      manager,
    )

  assert exc_info.value.error_code == "TICKET_TARGET_ALREADY_SELECTED"


@pytest.mark.asyncio
async def test_current_assignee_can_return_ticket_to_dispatch(monkeypatch) -> None:
  from src.ticket.schemas import ReturnToDispatchAction

  db = AsyncMock()
  officer = _user(Role.OFFICER, office_id=uuid4())
  ticket = _ticket(uuid4(), coordinator_id=officer.id)
  ticket.office_id = officer.office_id
  staged: list[TicketEvent] = []
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id_for_update",
    AsyncMock(return_value=ticket),
  )
  _mock_event_writes(monkeypatch, staged, ticket)

  await TicketWorkflowCommandService.return_to_dispatch(
    db,
    ticket.id,
    ReturnToDispatchAction(
      action=TicketWorkflowAction.RETURN_TO_DISPATCH,
      reason="Wrong authority",
    ),
    officer,
  )

  assert ticket.office_id is None
  assert ticket.primary_officer_id is None
  assert ticket.workflow_state == TicketWorkflowState.RETURNED_TO_DISPATCH
  assert staged[-1].event_type == TicketEventType.TICKET_RETURNED_TO_DISPATCH
