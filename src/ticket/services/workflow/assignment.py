"""Dispatcher and manager assignment commands."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, WorkflowValidationException
from src.office.repository import OfficeRepository
from src.ticket.events import (
  PrimaryOfficerAssignedPayload,
  TicketDispatchedPayload, TicketEventType, TicketWorkflowState,
)
from src.ticket.schemas import (
  PrimaryOfficerAssignmentRequest,
  TicketDispatchRequest, TicketInternalDetailResponse,
)
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.loaders import require_ticket
from src.ticket.services.workflow.rules import require_active_staff
from src.user.models import Role, User

from src.ticket.services.workflow.queries import TicketWorkflowQueryService


class TicketAssignmentService:
  """Assigns offices and permanent primary officers to tickets."""

  @staticmethod
  async def dispatch_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketDispatchRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Assigns a central-inbox ticket to an active office."""

    if current_user.role != Role.DISPATCHER:
      raise ForbiddenException("Only dispatchers may route tickets")

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if ticket.primary_officer_id is not None or ticket.workflow_state not in {
      TicketWorkflowState.NEW,
      TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
    }:
      raise WorkflowValidationException(
        "Only tickets without a primary officer may be dispatched."
      )

    office = await OfficeRepository.get_by_id(db, request.office_id)
    if office is None or not office.is_active:
      raise WorkflowValidationException("The selected office is not active.")

    await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_DISPATCHED,
      payload=TicketDispatchedPayload(
        office_id=office.id,
        comment=request.comment,
      ),
    )
    return await TicketWorkflowQueryService._internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def assign_primary_officer(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: PrimaryOfficerAssignmentRequest,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Lets the responsible office manager select the permanent case owner."""

    if current_user.role != Role.MANAGER:
      raise ForbiddenException("Only managers may assign a primary officer")

    ticket = await require_ticket(db, ticket_id, for_update=True)
    if (
      ticket.workflow_state != TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT
      or ticket.office_id is None
      or ticket.primary_officer_id is not None
    ):
      raise WorkflowValidationException(
        "The ticket is not waiting for its initial primary officer."
      )
    if current_user.office_id != ticket.office_id:
      raise ForbiddenException("Only a manager of the assigned office may act")

    officer = await require_active_staff(
      db,
      request.primary_officer_id,
      roles={Role.OFFICER},
      error_message=(
        "The primary officer must be an active officer of the assigned office."
      ),
    )
    if officer.office_id != ticket.office_id:
      raise WorkflowValidationException(
        "The primary officer must be an active officer of the assigned office."
      )

    await TicketEventStore._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.PRIMARY_OFFICER_ASSIGNED,
      payload=PrimaryOfficerAssignedPayload(
        primary_officer_id=officer.id,
        comment=request.comment,
      ),
    )
    return await TicketWorkflowQueryService._internal_detail_response(
      db,
      ticket,
      current_user,
    )
