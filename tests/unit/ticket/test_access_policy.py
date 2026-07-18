from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from src.ticket.domain import (
  TicketCategory,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.services.access_policy import TicketAccessPolicy
from src.user.models import Role, User


def _user(role: Role, *, office_id=None) -> User:
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


def _ticket(state: TicketWorkflowState, *, office_id=None) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid4(),
    title="Road damage",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=uuid4(),
    office_id=office_id,
    visibility=TicketVisibility.PRIVATE,
    workflow_state=state,
    version=1,
    created_at=now,
    updated_at=now,
  )


def test_dispatcher_internal_access_is_limited_to_routing_states() -> None:
  dispatcher = _user(Role.DISPATCHER)

  assert TicketAccessPolicy.can_view_internal(
    _ticket(TicketWorkflowState.NEW),
    dispatcher,
  )
  assert TicketAccessPolicy.can_view_internal(
    _ticket(TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT),
    dispatcher,
  )
  assert not TicketAccessPolicy.can_view_internal(
    _ticket(TicketWorkflowState.IN_PROGRESS),
    dispatcher,
  )


def test_staff_queue_scope_includes_return_target() -> None:
  officer = _user(Role.OFFICER)
  expression = TicketProjectionRepository._staff_scope(officer)
  sql = str(
    expression.compile(
      dialect=postgresql.dialect(),
      compile_kwargs={"literal_binds": True},
    )
  )

  assert "return_to_user_id" in sql


def test_capabilities_use_the_same_owner_and_staff_rules() -> None:
  citizen = _user(Role.CITIZEN)
  ticket = _ticket(TicketWorkflowState.NEW)
  ticket.creator_user_id = citizen.id

  citizen_capabilities = TicketAccessPolicy.capabilities(ticket, citizen)
  assert citizen_capabilities.can_edit is True
  assert citizen_capabilities.can_manage_images is True
  assert citizen_capabilities.can_comment is True
  assert citizen_capabilities.can_view_internal is False

  officer = _user(Role.OFFICER, office_id=uuid4())
  ticket.office_id = officer.office_id
  ticket.workflow_state = TicketWorkflowState.IN_PROGRESS
  staff_capabilities = TicketAccessPolicy.capabilities(ticket, officer)

  assert staff_capabilities.can_edit is False
  assert staff_capabilities.can_manage_images is True
  assert staff_capabilities.can_comment is True
  assert staff_capabilities.can_view_internal is True
