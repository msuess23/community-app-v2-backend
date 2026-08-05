"""Authority-side work queues, details, events and allowed actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ForbiddenException, ResourceNotFoundException
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.office.repository import OfficeRepository
from src.ticket.domain import (
  TicketCategory,
  TicketLifecycleFilter,
  TicketStatus,
  TicketWorkflowAction,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketSortField
from src.ticket.repositories.event import TicketEventRepository
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.schemas import (
  TicketEventResponse,
  TicketInternalDetailResponse,
  TicketInternalResponse,
  TicketWorkflowOptionsResponse,
)
from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketReferenceMapper, TicketResponseMapper
from src.ticket.services.timeline import latest_status_events
from src.ticket.services.workflow_policy import TicketWorkflowPolicy
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.roles import AUTHORITY_ROLES, CASE_WORKER_ROLES


_USER_REFERENCE_KEYS = frozenset(
  {
    "creator_user_id",
    "primary_officer_id",
    "previous_primary_officer_id",
    "new_primary_officer_id",
    "target_user_id",
    "return_to_user_id",
    "manager_user_id",
  }
)
_OFFICE_REFERENCE_KEYS = frozenset({"office_id", "previous_office_id"})


def _payload_uuid(value: object) -> UUID | None:
  """Normalize UUID values serialized as strings in JSONB payloads."""

  if isinstance(value, UUID):
    return value
  if isinstance(value, str):
    try:
      return UUID(value)
    except ValueError:
      return None
  return None


class TicketWorkflowQueryService:
  """Serve administrative workflow views without mutating the aggregate."""

  @staticmethod
  def _allowed_actions(ticket: Ticket, current_user: User) -> list[TicketWorkflowAction]:
    """Compatibility wrapper around the shared workflow policy."""

    return TicketWorkflowPolicy.allowed_actions(ticket, current_user)

  @staticmethod
  async def internal_detail_response(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Build one internal detail including server-computed actions."""

    refreshed_ticket = await TicketProjectionRepository.get_by_id(db, ticket.id)
    ticket = refreshed_ticket or ticket
    latest = latest_status_events(await TicketEventRepository.get_events(db, ticket.id))
    internal = TicketResponseMapper.to_internal_ticket(
      ticket,
      current_status_event=latest.get(ticket.id),
      current_user=current_user,
    )
    return TicketInternalDetailResponse(
      **internal.model_dump(),
      allowed_actions=TicketWorkflowPolicy.allowed_actions(ticket, current_user),
    )

  @staticmethod
  async def list_internal_tickets(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    lifecycle: TicketLifecycleFilter = TicketLifecycleFilter.ACTIVE,
    workflow_state: TicketWorkflowState | None = None,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    office_id: uuid.UUID | None = None,
    creator_user_id: uuid.UUID | None = None,
    primary_officer_id: uuid.UUID | None = None,
    current_assignee_id: uuid.UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.UPDATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> PaginatedResponse[TicketInternalResponse]:
    """List role-scoped active tickets or the searchable authority archive."""

    if current_user.role not in AUTHORITY_ROLES:
      raise ForbiddenException("This account has no internal ticket access")

    tickets, total = await TicketProjectionRepository.get_staff_page(
      db,
      current_user=current_user,
      page=page,
      size=size,
      lifecycle=lifecycle,
      workflow_state=workflow_state,
      status=status,
      category=category,
      office_id=office_id,
      creator_user_id=creator_user_id,
      primary_officer_id=primary_officer_id,
      current_assignee_id=current_assignee_id,
      created_from=created_from,
      created_to=created_to,
      updated_from=updated_from,
      updated_to=updated_to,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    latest = latest_status_events(
      await TicketEventRepository.get_events_for_tickets(
        db,
        [ticket.id for ticket in tickets],
      )
    )
    data = [
      TicketResponseMapper.to_internal_ticket(
        ticket,
        current_status_event=latest.get(ticket.id),
        current_user=current_user,
      )
      for ticket in tickets
    ]
    return PaginatedResponse.create(data=data, total=total, page=page, size=size)

  @staticmethod
  async def get_internal_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketInternalDetailResponse:
    """Return the workflow projection and available actions."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or not TicketAccessPolicy.can_view_internal(ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    return await TicketWorkflowQueryService.internal_detail_response(
      db,
      ticket,
      current_user,
    )

  @staticmethod
  async def get_workflow_options(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
  ) -> TicketWorkflowOptionsResponse:
    """Return only targets selectable for the actor's current actions."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or not TicketAccessPolicy.can_view_internal(ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")

    actions = set(TicketWorkflowPolicy.allowed_actions(ticket, current_user))
    offices = []
    primary_officers: list[User] = []
    processing_targets: list[User] = []
    escalation_targets: list[User] = []

    if TicketWorkflowAction.DISPATCH in actions:
      offices = await OfficeRepository.get_active_offices(db)
    if actions.intersection(
      {
        TicketWorkflowAction.ASSIGN_PRIMARY_OFFICER,
        TicketWorkflowAction.REASSIGN_PRIMARY_OFFICER,
      }
    ):
      primary_officers = await UserRepository.get_active_authority_users(
        db,
        roles={Role.OFFICER},
        office_id=ticket.office_id,
      )
      primary_officers = [
        user
        for user in primary_officers
        if TicketWorkflowPolicy.primary_officer_is_eligible(ticket, user)
        and user.id != ticket.primary_officer_id
      ]
    if actions.intersection(
      {
        TicketWorkflowAction.FORWARD,
        TicketWorkflowAction.REQUEST_COSIGNATURE,
      }
    ):
      processing_targets = await UserRepository.get_active_authority_users(
        db,
        roles=set(CASE_WORKER_ROLES),
      )
      processing_targets = [
        user
        for user in processing_targets
        if user.id != current_user.id
        and TicketWorkflowPolicy.processing_target_is_eligible(user)
      ]
    if TicketWorkflowAction.ESCALATE in actions:
      escalation_targets = await UserRepository.get_active_authority_users(
        db,
        roles={Role.MANAGER},
      )
      escalation_targets = [
        user
        for user in escalation_targets
        if user.id != current_user.id
        and TicketWorkflowPolicy.escalation_target_is_eligible(user)
      ]

    all_staff = primary_officers + processing_targets + escalation_targets
    office_ids = {user.office_id for user in all_staff if user.office_id is not None}
    office_map = {
      office.id: office
      for office in await OfficeRepository.get_by_ids(db, office_ids)
    }

    return TicketWorkflowOptionsResponse(
      ticket_id=ticket.id,
      version=ticket.version,
      offices=[
        reference
        for office in offices
        if (reference := TicketReferenceMapper.office(office)) is not None
      ],
      primary_officers=[
        TicketReferenceMapper.staff(user, office_map) for user in primary_officers
      ],
      forward_targets=[
        TicketReferenceMapper.staff(user, office_map) for user in processing_targets
      ]
      if TicketWorkflowAction.FORWARD in actions
      else [],
      cosignature_targets=[
        TicketReferenceMapper.staff(user, office_map) for user in processing_targets
      ]
      if TicketWorkflowAction.REQUEST_COSIGNATURE in actions
      else [],
      escalation_targets=[
        TicketReferenceMapper.staff(user, office_map) for user in escalation_targets
      ],
      completion_outcomes=(
        TicketWorkflowPolicy.completion_outcomes(current_user)
        if TicketWorkflowAction.COMPLETE in actions
        else []
      ),
    )

  @staticmethod
  async def get_internal_events(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User,
    *,
    page: int,
    size: int,
  ) -> PaginatedResponse[TicketEventResponse]:
    """Return a chronological page of events to authorized staff."""

    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    if ticket is None or not TicketAccessPolicy.can_view_internal(ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events, total = await TicketEventRepository.get_event_page(
      db,
      ticket.id,
      page=page,
      size=size,
    )

    user_ids: set[UUID] = set()
    office_ids: set[UUID] = set()
    for event in events:
      for key, value in event.payload.items():
        identifier = _payload_uuid(value)
        if identifier is None:
          continue
        if key in _USER_REFERENCE_KEYS:
          user_ids.add(identifier)
        elif key in _OFFICE_REFERENCE_KEYS:
          office_ids.add(identifier)
    loaded_users = await UserRepository.get_by_ids(db, user_ids)
    users = {key: user for user in loaded_users for key in (user.id, str(user.id))}
    loaded_offices = await OfficeRepository.get_by_ids(db, office_ids)
    offices = {
      key: office for office in loaded_offices for key in (office.id, str(office.id))
    }

    return PaginatedResponse.create(
      data=[
        TicketResponseMapper.to_event(event, users=users, offices=offices)
        for event in events
      ],
      total=total,
      page=page,
      size=size,
    )
