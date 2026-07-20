"""Ticket-link validation for citizen appointment bookings."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.appointment.service import AppointmentService
from src.core.exceptions import DomainValidationException, ResourceNotFoundException
from src.ticket.domain import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.user.models import Role, User


def _citizen() -> User:
  return User(
    id=uuid.uuid4(),
    email="appointment.link@example.com",
    hashed_password="hash",
    first_name="Ticket",
    last_name="Owner",
    role=Role.CITIZEN,
    is_active=True,
  )


def _ticket(citizen_id: uuid.UUID, office_id: uuid.UUID) -> Ticket:
  now = datetime.now(timezone.utc)
  return Ticket(
    id=uuid.uuid4(),
    title="Linked ticket",
    category=TicketCategory.INFRASTRUCTURE,
    creator_user_id=citizen_id,
    office_id=office_id,
    visibility=TicketVisibility.PRIVATE,
    public_status=TicketStatus.IN_PROGRESS,
    workflow_state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    version=1,
    created_at=now,
    updated_at=now,
  )


@pytest.mark.asyncio
async def test_ticket_link_must_use_the_responsible_office(monkeypatch) -> None:
  citizen = _citizen()
  responsible_office_id = uuid.uuid4()
  ticket = _ticket(citizen.id, responsible_office_id)
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )

  with pytest.raises(DomainValidationException) as exc:
    await AppointmentService._validate_ticket_link(
      AsyncMock(),
      ticket_id=ticket.id,
      citizen=citizen,
      office_id=uuid.uuid4(),
    )

  assert exc.value.error_code == "TICKET_OFFICE_MISMATCH"


@pytest.mark.asyncio
async def test_foreign_ticket_is_hidden_as_not_found(monkeypatch) -> None:
  citizen = _citizen()
  office_id = uuid.uuid4()
  ticket = _ticket(uuid.uuid4(), office_id)
  monkeypatch.setattr(
    "src.ticket.repositories.ticket.TicketProjectionRepository.get_by_id",
    AsyncMock(return_value=ticket),
  )

  with pytest.raises(ResourceNotFoundException) as exc:
    await AppointmentService._validate_ticket_link(
      AsyncMock(),
      ticket_id=ticket.id,
      citizen=citizen,
      office_id=office_id,
    )

  assert exc.value.error_code == "TICKET_NOT_FOUND"
