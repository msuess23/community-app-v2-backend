from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock
from uuid import UUID, uuid4

import pytest

from src.office.models import Office
from src.ticket.domain import (
  TicketCategory,
  TicketCompletionOutcome,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.ticket.services.workflow_queries import TicketWorkflowQueryService
from src.user.models import Role, User


def _user(
  role: Role,
  *,
  office_id: UUID | None = None,
  first_name: str = "Test",
  last_name: str | None = None,
  is_active: bool = True,
) -> User:
  return User(
    id=uuid4(),
    email=f"{uuid4()}@example.com",
    hashed_password="hash",
    first_name=first_name,
    last_name=last_name or role.value,
    role=role,
    office_id=office_id,
    is_active=is_active,
  )


def _ticket(
  actor: User,
  *,
  office_id: UUID | None,
  state: TicketWorkflowState,
  primary_officer_id: UUID | None = None,
) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid4(),
    title="Pothole",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=uuid4(),
    office_id=office_id,
    visibility=TicketVisibility.PUBLIC,
    public_status=(
      TicketStatus.OPEN if state == TicketWorkflowState.NEW else TicketStatus.IN_PROGRESS
    ),
    workflow_state=state,
    primary_officer_id=primary_officer_id,
    current_assignee_id=actor.id if state == TicketWorkflowState.IN_PROGRESS else None,
    version=4,
    created_at=now,
    updated_at=now,
  )


@pytest.mark.asyncio
async def test_dispatcher_options_only_expose_active_dispatch_offices(monkeypatch) -> None:
  dispatcher = _user(Role.DISPATCHER)
  ticket = _ticket(
    dispatcher,
    office_id=None,
    state=TicketWorkflowState.RETURNED_TO_DISPATCH,
  )
  office = Office(id=uuid4(), name="Building Office", is_active=True)

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.office.repository.OfficeRepository.get_active_offices",
    AsyncMock(return_value=[office]),
  )

  response = await TicketWorkflowQueryService.get_workflow_options(
    AsyncMock(), ticket.id, dispatcher
  )

  assert response.version == ticket.version
  assert [(item.id, item.name) for item in response.offices] == [
    (office.id, office.name)
  ]
  assert response.primary_officers == []
  assert response.forward_targets == []
  assert response.cosignature_targets == []
  assert response.escalation_targets == []
  assert response.completion_outcomes == []


@pytest.mark.asyncio
async def test_manager_options_filter_primary_officers_to_assigned_office(monkeypatch) -> None:
  office_id = uuid4()
  manager = _user(Role.MANAGER, office_id=office_id)
  current = _user(Role.OFFICER, office_id=office_id, last_name="Current")
  replacement = _user(Role.OFFICER, office_id=office_id, last_name="Replacement")
  ticket = _ticket(
    manager,
    office_id=office_id,
    state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
  )
  office = Office(id=office_id, name="Building Office", is_active=True)

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )
  active_users = AsyncMock(return_value=[current, replacement])
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_active_authority_users",
    active_users,
  )
  monkeypatch.setattr(
    "src.office.repository.OfficeRepository.get_by_ids",
    AsyncMock(return_value=[office]),
  )

  response = await TicketWorkflowQueryService.get_workflow_options(
    AsyncMock(), ticket.id, manager
  )

  active_users.assert_awaited_once_with(
    ANY,
    roles={Role.OFFICER},
    office_id=office_id,
  )
  assert {item.id for item in response.primary_officers} == {
    current.id,
    replacement.id,
  }
  assert all(item.office and item.office.id == office_id for item in response.primary_officers)


@pytest.mark.asyncio
async def test_officer_options_support_cross_office_targets_and_role_outcome(monkeypatch) -> None:
  actor_office_id = uuid4()
  other_office_id = uuid4()
  officer = _user(Role.OFFICER, office_id=actor_office_id, last_name="Actor")
  other_officer = _user(Role.OFFICER, office_id=other_office_id, last_name="Other")
  manager = _user(Role.MANAGER, office_id=other_office_id, last_name="Manager")
  ticket = _ticket(
    officer,
    office_id=actor_office_id,
    state=TicketWorkflowState.IN_PROGRESS,
    primary_officer_id=officer.id,
  )
  offices = [
    Office(id=actor_office_id, name="Road Office", is_active=True),
    Office(id=other_office_id, name="Environment Office", is_active=True),
  ]

  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )
  monkeypatch.setattr(
    "src.user.repository.UserRepository.get_active_authority_users",
    AsyncMock(side_effect=[[officer, other_officer, manager], [manager]]),
  )
  monkeypatch.setattr(
    "src.office.repository.OfficeRepository.get_by_ids",
    AsyncMock(return_value=offices),
  )

  response = await TicketWorkflowQueryService.get_workflow_options(
    AsyncMock(), ticket.id, officer
  )

  assert officer.id not in {item.id for item in response.forward_targets}
  assert {item.id for item in response.forward_targets} == {
    other_officer.id,
    manager.id,
  }
  assert {item.id for item in response.cosignature_targets} == {
    other_officer.id,
    manager.id,
  }
  assert [item.id for item in response.escalation_targets] == [manager.id]
  assert response.completion_outcomes == [TicketCompletionOutcome.RESOLVED]
