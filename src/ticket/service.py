"""Application services for the event-sourced ticket aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.models import Address
from src.address.schemas import AddressCreate, AddressResponse
from src.address.service import AddressService
from src.core.exceptions import (
  ConflictException,
  ForbiddenException,
  ResourceNotFoundException,
  WorkflowValidationException,
)
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.ticket.events import (
  AddressSnapshot,
  TicketAggregateState,
  TicketCancelledPayload,
  TicketCategory,
  TicketDetailsUpdatedPayload,
  TicketEventType,
  TicketStatus,
  TicketSubmittedPayload,
  TicketCommentedPayload,
  TicketVisibility,
  TicketWorkflowState,
  evolve_ticket,
)
from src.ticket.models import Ticket, TicketEvent, TicketSortField
from src.ticket.repository import TicketRepository
from src.ticket.schemas import (
  TicketCancelRequest,
  TicketCreateRequest,
  TicketResponse,
  TicketStatusResponse,
  TicketUpdateRequest,
)
from src.user.models import Role, User


class TicketService:
  """Coordinates authorization, event persistence and projection updates."""

  @staticmethod
  def _address_snapshot(address: Address | AddressCreate | None) -> AddressSnapshot | None:
    """Converts an address entity or request into an immutable event value."""

    if address is None:
      return None
    return AddressSnapshot(
      street=address.street,
      house_number=address.house_number,
      zip_code=address.zip_code,
      city=address.city,
      latitude=address.latitude,
      longitude=address.longitude,
    )

  @staticmethod
  def _state_from_ticket(ticket: Ticket) -> TicketAggregateState:
    """Maps the current SQLAlchemy projection back to pure aggregate state."""

    return TicketAggregateState(
      title=ticket.title,
      description=ticket.description,
      category=ticket.category,
      creator_user_id=ticket.creator_user_id,
      office_id=ticket.office_id,
      address=TicketService._address_snapshot(ticket.address),
      visibility=ticket.visibility,
      public_status=ticket.public_status,
      public_status_message=ticket.public_status_message,
      workflow_state=ticket.workflow_state,
      primary_officer_id=ticket.primary_officer_id,
      current_responsible_user_id=ticket.current_responsible_user_id,
      pending_return_to_user_id=ticket.pending_return_to_user_id,
      version=ticket.version,
      created_at=ticket.created_at,
      updated_at=ticket.updated_at,
      resolved_at=ticket.resolved_at,
      cancelled_at=ticket.cancelled_at,
    )

  @staticmethod
  def _sync_projection(ticket: Ticket, state: TicketAggregateState) -> None:
    """Copies aggregate scalar values to the query-oriented read model."""

    ticket.title = state.title
    ticket.description = state.description
    ticket.category = state.category
    ticket.office_id = state.office_id
    ticket.visibility = state.visibility
    ticket.public_status = state.public_status
    ticket.public_status_message = state.public_status_message
    ticket.workflow_state = state.workflow_state
    ticket.primary_officer_id = state.primary_officer_id
    ticket.current_responsible_user_id = state.current_responsible_user_id
    ticket.pending_return_to_user_id = state.pending_return_to_user_id
    ticket.version = state.version
    ticket.created_at = state.created_at
    ticket.updated_at = state.updated_at
    ticket.resolved_at = state.resolved_at
    ticket.cancelled_at = state.cancelled_at

  @staticmethod
  def _event_visibility(
    event_type: TicketEventType,
    state: TicketAggregateState,
    payload,
  ) -> tuple[bool, TicketStatus | None, str | None]:
    """Defines which workflow changes become part of the citizen timeline."""

    if event_type in {
      TicketEventType.TICKET_SUBMITTED,
      TicketEventType.TICKET_DISPATCHED,
      TicketEventType.CITIZEN_RESPONSE_REQUESTED,
      TicketEventType.CITIZEN_RESPONDED,
      TicketEventType.ESCALATION_APPROVED,
      TicketEventType.TICKET_RESOLVED,
      TicketEventType.TICKET_REJECTED,
      TicketEventType.TICKET_CANCELLED,
    }:
      return True, state.public_status, state.public_status_message
    if event_type == TicketEventType.TICKET_DETAILS_UPDATED:
      return True, None, None
    if event_type == TicketEventType.TICKET_COMMENTED:
      comment = payload
      assert isinstance(comment, TicketCommentedPayload)
      return not comment.is_internal, None, None
    return False, None, None

  @staticmethod
  def _build_event(
    *,
    ticket_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    event_type: TicketEventType,
    payload,
    state: TicketAggregateState,
    occurred_at: datetime,
  ) -> TicketEvent:
    """Builds one append-only event after the new aggregate state is known."""

    citizen_visible, public_status, public_message = TicketService._event_visibility(
      event_type,
      state,
      payload,
    )
    return TicketEvent(
      id=uuid.uuid4(),
      ticket_id=ticket_id,
      sequence_number=state.version,
      event_type=event_type,
      actor_user_id=actor_user_id,
      occurred_at=occurred_at,
      payload=payload.model_dump(mode="json", exclude_unset=True),
      citizen_visible=citizen_visible,
      public_status=public_status,
      public_message=public_message,
    )

  @staticmethod
  async def _append_event(
    db: AsyncSession,
    ticket: Ticket,
    *,
    actor_user_id: uuid.UUID,
    event_type: TicketEventType,
    payload,
    occurred_at: datetime | None = None,
  ) -> TicketEvent:
    """Atomically appends an event and updates the in-transaction projection."""

    event_time = occurred_at or datetime.now(timezone.utc)
    current_state = TicketService._state_from_ticket(ticket)
    next_state = evolve_ticket(
      current_state,
      event_type,
      payload,
      occurred_at=event_time,
    )

    # The event and projection are staged in the same request transaction.  A
    # failure in either write therefore rolls both changes back together.
    TicketService._sync_projection(ticket, next_state)
    event = TicketService._build_event(
      ticket_id=ticket.id,
      actor_user_id=actor_user_id,
      event_type=event_type,
      payload=payload,
      state=next_state,
      occurred_at=event_time,
    )
    TicketRepository.add(db, ticket)
    TicketRepository.add_event(db, event)
    await db.flush()
    return event

  @staticmethod
  async def _can_view_ticket(
    db: AsyncSession,
    ticket: Ticket,
    current_user: User | None,
  ) -> bool:
    """Checks public, creator and authority-side access to one ticket."""

    if ticket.visibility == TicketVisibility.PUBLIC:
      return True
    if current_user is None:
      return False
    if current_user.id == ticket.creator_user_id:
      return True
    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role in {Role.OFFICER, Role.MANAGER}:
      if current_user.id in {
        ticket.primary_officer_id,
        ticket.current_responsible_user_id,
      }:
        return True
      if current_user.office_id is not None and current_user.office_id == ticket.office_id:
        return True
      return await TicketRepository.has_open_work_item_for_user(
        db,
        ticket.id,
        current_user.id,
      )
    return False

  @staticmethod
  def _status_response(event: TicketEvent | None) -> TicketStatusResponse | None:
    """Converts a public event into the former Ktor status DTO shape."""

    if event is None or event.public_status is None:
      return None
    return TicketStatusResponse(
      id=event.id,
      status=event.public_status,
      message=event.public_message,
      created_by_user_id=event.actor_user_id,
      created_at=event.occurred_at,
    )

  @staticmethod
  def _ticket_response(
    ticket: Ticket,
    *,
    current_status_event: TicketEvent | None,
    current_user: User | None,
  ) -> TicketResponse:
    """Builds a stable citizen-facing response without leaking workflow tasks."""

    can_edit = (
      current_user is not None
      and current_user.id == ticket.creator_user_id
      and ticket.workflow_state == TicketWorkflowState.NEW
    )
    return TicketResponse(
      id=ticket.id,
      title=ticket.title,
      description=ticket.description,
      category=ticket.category,
      office_id=ticket.office_id,
      creator_user_id=ticket.creator_user_id,
      address=(
        AddressResponse.model_validate(ticket.address)
        if ticket.address is not None
        else None
      ),
      visibility=ticket.visibility,
      created_at=ticket.created_at,
      current_status=TicketService._status_response(current_status_event),
      votes_count=0,
      user_voted=(False if current_user is not None else None),
      image_url=None,
      can_edit=can_edit,
      version=ticket.version,
    )

  @staticmethod
  async def create_ticket(
    db: AsyncSession,
    request: TicketCreateRequest,
    current_user: User,
  ) -> TicketResponse:
    """Creates a central-inbox ticket from one citizen submission event."""

    if current_user.role != Role.CITIZEN:
      raise ForbiddenException("Only citizens may submit tickets")

    occurred_at = datetime.now(timezone.utc)
    payload = TicketSubmittedPayload(
      title=request.title,
      description=request.description,
      category=request.category,
      creator_user_id=current_user.id,
      address=(
        TicketService._address_snapshot(request.address)
        if request.address is not None
        else None
      ),
      visibility=request.visibility,
    )
    state = evolve_ticket(
      None,
      TicketEventType.TICKET_SUBMITTED,
      payload,
      occurred_at=occurred_at,
    )

    ticket = Ticket(id=uuid.uuid4(), creator_user_id=current_user.id)
    TicketService._sync_projection(ticket, state)
    if request.address is not None:
      ticket.address = AddressService.create_address_entity(request.address)

    event = TicketService._build_event(
      ticket_id=ticket.id,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_SUBMITTED,
      payload=payload,
      state=state,
      occurred_at=occurred_at,
    )
    TicketRepository.add(db, ticket)
    TicketRepository.add_event(db, event)
    await db.flush()
    return TicketService._ticket_response(
      ticket,
      current_status_event=event,
      current_user=current_user,
    )

  @staticmethod
  async def list_public_tickets(
    db: AsyncSession,
    *,
    current_user: User | None,
    page: int,
    size: int,
    office_id: uuid.UUID | None = None,
    category: TicketCategory | None = None,
    status: TicketStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> PaginatedResponse[TicketResponse]:
    """Lists public community tickets with Ktor-compatible filters."""

    tickets, total = await TicketRepository.get_public_page(
      db,
      page=page,
      size=size,
      office_id=office_id,
      category=category,
      status=status,
      created_from=created_from,
      created_to=created_to,
      bbox=bbox,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    latest_events = await TicketRepository.get_latest_public_events(
      db,
      [ticket.id for ticket in tickets],
    )
    data = [
      TicketService._ticket_response(
        ticket,
        current_status_event=latest_events.get(ticket.id),
        current_user=current_user,
      )
      for ticket in tickets
    ]
    return PaginatedResponse.create(data=data, total=total, page=page, size=size)

  @staticmethod
  async def list_my_tickets(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> PaginatedResponse[TicketResponse]:
    """Lists all public and private tickets owned by the current citizen."""

    tickets, total = await TicketRepository.get_creator_page(
      db,
      creator_user_id=current_user.id,
      page=page,
      size=size,
      status=status,
      category=category,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    latest_events = await TicketRepository.get_latest_public_events(
      db,
      [ticket.id for ticket in tickets],
    )
    data = [
      TicketService._ticket_response(
        ticket,
        current_status_event=latest_events.get(ticket.id),
        current_user=current_user,
      )
      for ticket in tickets
    ]
    return PaginatedResponse.create(data=data, total=total, page=page, size=size)

  @staticmethod
  async def get_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> TicketResponse:
    """Returns a public ticket or a private ticket visible to the caller."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketService._can_view_ticket(db, ticket, current_user):
      raise ResourceNotFoundException(
        "Ticket not found",
        error_code="TICKET_NOT_FOUND",
      )
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketService._ticket_response(
      ticket,
      current_status_event=latest.get(ticket.id),
      current_user=current_user,
    )

  @staticmethod
  async def update_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketUpdateRequest,
    current_user: User,
  ) -> TicketResponse:
    """Appends a details event while a citizen ticket is still undispatched."""

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    if current_user.id != ticket.creator_user_id:
      raise ForbiddenException("Only the ticket creator may edit this ticket")
    if ticket.workflow_state != TicketWorkflowState.NEW:
      raise WorkflowValidationException(
        "A ticket can only be edited before it is dispatched."
      )

    changes = request.model_dump(exclude_unset=True)
    if not changes:
      latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
      return TicketService._ticket_response(
        ticket,
        current_status_event=latest.get(ticket.id),
        current_user=current_user,
      )

    if "address" in request.model_fields_set:
      address_request = request.address
      old_address = ticket.address
      ticket.address = (
        AddressService.create_address_entity(address_request)
        if address_request is not None
        else None
      )
      # delete-orphan removes the old address after the relationship is replaced.
      if old_address is not None and ticket.address is None:
        await db.flush()

    payload_values = dict(changes)
    if "address" in request.model_fields_set:
      payload_values["address"] = (
        TicketService._address_snapshot(request.address)
        if request.address is not None
        else None
      )
    payload = TicketDetailsUpdatedPayload.model_validate(payload_values)
    event = await TicketService._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_DETAILS_UPDATED,
      payload=payload,
    )
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketService._ticket_response(
      ticket,
      current_status_event=latest.get(ticket.id) or event,
      current_user=current_user,
    )

  @staticmethod
  async def cancel_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    request: TicketCancelRequest,
    current_user: User,
  ) -> None:
    """Cancels a ticket only while it is still waiting in the central inbox."""

    ticket = await TicketRepository.get_by_id_for_update(db, ticket_id)
    if ticket is None:
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    if current_user.id != ticket.creator_user_id:
      raise ForbiddenException("Only the ticket creator may cancel this ticket")
    if ticket.workflow_state != TicketWorkflowState.NEW:
      raise ConflictException(
        "A dispatched ticket can no longer be cancelled by the citizen.",
        error_code="TICKET_ALREADY_IN_PROCESS",
      )

    await TicketService._append_event(
      db,
      ticket,
      actor_user_id=current_user.id,
      event_type=TicketEventType.TICKET_CANCELLED,
      payload=TicketCancelledPayload(reason=request.reason),
    )

  @staticmethod
  async def get_status_history(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> list[TicketStatusResponse]:
    """Returns only public-status events, not the internal authority workflow."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketService._can_view_ticket(db, ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events = await TicketRepository.get_events(
      db,
      ticket_id,
      citizen_visible_only=True,
    )
    return [
      status
      for event in events
      if (status := TicketService._status_response(event)) is not None
    ]

  @staticmethod
  async def get_current_status(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> TicketStatusResponse | None:
    """Returns the latest citizen-visible processing status."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketService._can_view_ticket(db, ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketService._status_response(latest.get(ticket.id))
