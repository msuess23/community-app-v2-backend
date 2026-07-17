"""Citizen and public queries against the ticket read model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundException
from src.core.filters import SortOrder
from src.core.schemas import PaginatedResponse
from src.ticket.events import (
  TicketCategory,
  TicketStatus,
)
from src.ticket.models import TicketSortField
from src.ticket.repository import TicketRepository
from src.ticket.schemas import TicketResponse, TicketStatusResponse
from src.user.models import User

from src.ticket.services.access_policy import TicketAccessPolicy
from src.ticket.services.mapper import TicketResponseMapper


class TicketQueryService:
  """Serves public, creator and status views from the ticket projection."""

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
      TicketResponseMapper.to_public_ticket(
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
      TicketResponseMapper.to_public_ticket(
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
    if ticket is None or not await TicketAccessPolicy.can_view(db, ticket, current_user):
      raise ResourceNotFoundException(
        "Ticket not found",
        error_code="TICKET_NOT_FOUND",
      )
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketResponseMapper.to_public_ticket(
      ticket,
      current_status_event=latest.get(ticket.id),
      current_user=current_user,
    )

  @staticmethod
  async def get_status_history(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> list[TicketStatusResponse]:
    """Returns only public-status events, not the internal authority workflow."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view(db, ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    events = await TicketRepository.get_events(
      db,
      ticket_id,
      citizen_visible_only=True,
    )
    return [
      status
      for event in events
      if (status := TicketResponseMapper.to_status(event)) is not None
    ]

  @staticmethod
  async def get_current_status(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    current_user: User | None,
  ) -> TicketStatusResponse | None:
    """Returns the latest citizen-visible processing status."""

    ticket = await TicketRepository.get_by_id(db, ticket_id)
    if ticket is None or not await TicketAccessPolicy.can_view(db, ticket, current_user):
      raise ResourceNotFoundException("Ticket not found", error_code="TICKET_NOT_FOUND")
    latest = await TicketRepository.get_latest_public_events(db, [ticket.id])
    return TicketResponseMapper.to_status(latest.get(ticket.id))
