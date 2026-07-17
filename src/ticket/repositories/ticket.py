"""Queries for the current ticket projection and list views."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.address.models import Address
from src.core.filters import SortOrder, apply_bbox_filter, apply_search_filter
from src.ticket.domain import (
  TicketCategory, TicketStatus, TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketSortField
from src.user.models import Role, User

class TicketProjectionRepository:
  """Persists and queries the current ticket read model."""

  SORT_COLUMNS = {
    TicketSortField.CREATED_AT: Ticket.created_at,
    TicketSortField.UPDATED_AT: Ticket.updated_at,
    TicketSortField.TITLE: Ticket.title,
    TicketSortField.STATUS: Ticket.public_status,
  }

  @staticmethod
  def add(db: AsyncSession, ticket: Ticket) -> None:
    """Stages a ticket projection for insertion or update."""

    db.add(ticket)

  @staticmethod
  async def get_by_id(db: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    """Loads a ticket and its owned address without acquiring a row lock."""

    result = await db.execute(
      select(Ticket)
      .options(
        selectinload(Ticket.address),
        selectinload(Ticket.images),
      )
      .where(Ticket.id == ticket_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id_for_update(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> Ticket | None:
    """Locks the projection while a new event and state update are appended."""

    result = await db.execute(
      select(Ticket)
      .options(
        selectinload(Ticket.address),
        selectinload(Ticket.images),
      )
      .where(Ticket.id == ticket_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_public_page(
    db: AsyncSession,
    *,
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
  ) -> tuple[list[Ticket], int]:
    """Return public community tickets using the documented filters."""

    query = (
      select(Ticket)
      .options(
        selectinload(Ticket.address),
        selectinload(Ticket.images),
      )
      .where(Ticket.visibility == TicketVisibility.PUBLIC)
    )
    query = apply_search_filter(query, search, Ticket.title, Ticket.description)

    if office_id is not None:
      query = query.where(Ticket.office_id == office_id)
    if category is not None:
      query = query.where(Ticket.category == category)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if created_from is not None:
      query = query.where(Ticket.created_at >= created_from)
    if created_to is not None:
      query = query.where(Ticket.created_at <= created_to)
    if bbox is not None:
      query = query.outerjoin(Address, Ticket.address_id == Address.id)
      query = apply_bbox_filter(query, Address, bbox)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())

    sort_column = TicketProjectionRepository.SORT_COLUMNS[sort_by]
    ordering = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
    query = query.order_by(ordering, Ticket.id.asc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    return list(result.scalars().unique().all()), total

  @staticmethod
  async def get_creator_page(
    db: AsyncSession,
    *,
    creator_user_id: uuid.UUID,
    page: int,
    size: int,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> tuple[list[Ticket], int]:
    """Returns every public or private ticket created by one citizen."""

    query = (
      select(Ticket)
      .options(
        selectinload(Ticket.address),
        selectinload(Ticket.images),
      )
      .where(Ticket.creator_user_id == creator_user_id)
    )
    query = apply_search_filter(query, search, Ticket.title, Ticket.description)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if category is not None:
      query = query.where(Ticket.category == category)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())

    sort_column = TicketProjectionRepository.SORT_COLUMNS[sort_by]
    ordering = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
    query = query.order_by(ordering, Ticket.id.asc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    return list(result.scalars().unique().all()), total

  @staticmethod
  async def get_staff_page(
    db: AsyncSession,
    *,
    current_user: User,
    page: int,
    size: int,
    workflow_state: TicketWorkflowState | None = None,
    status: TicketStatus | None = None,
    category: TicketCategory | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.UPDATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> tuple[list[Ticket], int]:
    """Returns a role-scoped work queue for the administrative client.

    Dispatchers see the central routing queue. Managers see active tickets of
    their office as well as cross-office tasks assigned to them. Officers see
    tickets they own, coordinate, or have an open parallel task for.
    """

    query = select(Ticket).options(
        selectinload(Ticket.address),
        selectinload(Ticket.images),
      )
    if current_user.role == Role.DISPATCHER:
      query = query.where(
        Ticket.workflow_state.in_(
          {
            TicketWorkflowState.NEW,
            TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
          }
        )
      )
    elif current_user.role == Role.MANAGER:
      query = query.where(
        Ticket.workflow_state != TicketWorkflowState.COMPLETED,
        or_(
          Ticket.office_id == current_user.office_id,
          Ticket.primary_officer_id == current_user.id,
          Ticket.current_assignee_id == current_user.id,
        ),
      )
    elif current_user.role == Role.OFFICER:
      query = query.where(
        Ticket.workflow_state != TicketWorkflowState.COMPLETED,
        or_(
          Ticket.primary_officer_id == current_user.id,
          Ticket.current_assignee_id == current_user.id,
        ),
      )
    else:
      # The service blocks this branch, but the defensive false predicate keeps
      # accidental direct repository use from exposing authority-side data.
      query = query.where(Ticket.id.is_(None))

    query = apply_search_filter(query, search, Ticket.title, Ticket.description)
    if workflow_state is not None:
      query = query.where(Ticket.workflow_state == workflow_state)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if category is not None:
      query = query.where(Ticket.category == category)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int((await db.execute(count_query)).scalar_one())

    sort_column = TicketProjectionRepository.SORT_COLUMNS[sort_by]
    ordering = sort_column.desc() if order == SortOrder.DESC else sort_column.asc()
    query = query.order_by(ordering, Ticket.id.asc())
    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    return list(result.scalars().unique().all()), total
