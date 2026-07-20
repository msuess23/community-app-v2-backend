"""Queries for the current ticket projection and list views."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar, Mapping

from sqlalchemy import exists, false, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from src.address.models import Address
from src.core.filters import SortOrder, apply_bbox_filter, apply_search_filter
from src.core.pagination import execute_page
from src.ticket.domain import (
  TicketCategory,
  TicketLifecycleFilter,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket, TicketSortField
from src.user.models import Role, User


class TicketProjectionRepository:
  """Persists and queries the current ticket read model."""

  SORT_COLUMNS: ClassVar[Mapping[TicketSortField, InstrumentedAttribute[Any]]] = {
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
  def _detail_query():
    return select(Ticket).options(
      selectinload(Ticket.address),
      selectinload(Ticket.images),
    )

  @staticmethod
  async def get_by_id(db: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    """Loads a ticket and its response relations without acquiring a row lock."""

    result = await db.execute(
      TicketProjectionRepository._detail_query().where(Ticket.id == ticket_id)
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id_for_update(
    db: AsyncSession,
    ticket_id: uuid.UUID,
  ) -> Ticket | None:
    """Locks the projection while a new event and state update are appended."""

    result = await db.execute(
      TicketProjectionRepository._detail_query()
      .where(Ticket.id == ticket_id)
      .with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def has_active_user_dependency(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> bool:
    """Return whether an unfinished ticket still depends on one user."""

    dependency = or_(
      Ticket.creator_user_id == user_id,
      Ticket.primary_officer_id == user_id,
      Ticket.current_assignee_id == user_id,
      Ticket.return_to_user_id == user_id,
    )
    query = select(
      exists().where(
        Ticket.workflow_state != TicketWorkflowState.COMPLETED,
        dependency,
      )
    )
    return bool((await db.execute(query)).scalar_one())

  @staticmethod
  async def has_active_tickets_for_office(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> bool:
    """Return whether an office owns at least one unfinished ticket."""

    query = select(
      exists().where(
        Ticket.office_id == office_id,
        Ticket.workflow_state != TicketWorkflowState.COMPLETED,
      )
    )
    return bool((await db.execute(query)).scalar_one())

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
    bbox: tuple[float, float, float, float] | None = None,
    search: str | None = None,
    sort_by: TicketSortField = TicketSortField.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
  ) -> tuple[list[Ticket], int]:
    """Return public community tickets using the documented filters."""

    query = TicketProjectionRepository._detail_query().where(
      Ticket.visibility == TicketVisibility.PUBLIC
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

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=TicketProjectionRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Ticket.id,
      unique=True,
    )

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
    """Return every public or private ticket created by one citizen."""

    query = TicketProjectionRepository._detail_query().where(
      Ticket.creator_user_id == creator_user_id
    )
    query = apply_search_filter(query, search, Ticket.title, Ticket.description)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if category is not None:
      query = query.where(Ticket.category == category)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=TicketProjectionRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Ticket.id,
      unique=True,
    )

  @staticmethod
  def _staff_scope(current_user: User):
    """Build the immutable role scope used by all internal ticket searches."""

    if current_user.role == Role.DISPATCHER:
      return Ticket.workflow_state.in_(
        {
          TicketWorkflowState.NEW,
          TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
        }
      )

    if current_user.role == Role.MANAGER:
      return or_(
        Ticket.office_id == current_user.office_id,
        Ticket.primary_officer_id == current_user.id,
        Ticket.current_assignee_id == current_user.id,
        Ticket.return_to_user_id == current_user.id,
      )

    if current_user.role == Role.OFFICER:
      return or_(
        Ticket.primary_officer_id == current_user.id,
        Ticket.current_assignee_id == current_user.id,
        Ticket.return_to_user_id == current_user.id,
      )

    return false()

  @staticmethod
  async def get_staff_page(
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
  ) -> tuple[list[Ticket], int]:
    """Return a role-scoped internal page for active work or archive research."""

    query = TicketProjectionRepository._detail_query().where(
      TicketProjectionRepository._staff_scope(current_user)
    )
    if lifecycle == TicketLifecycleFilter.ACTIVE:
      query = query.where(Ticket.workflow_state != TicketWorkflowState.COMPLETED)
    elif lifecycle == TicketLifecycleFilter.COMPLETED:
      query = query.where(Ticket.workflow_state == TicketWorkflowState.COMPLETED)

    query = apply_search_filter(query, search, Ticket.title, Ticket.description)
    if workflow_state is not None:
      query = query.where(Ticket.workflow_state == workflow_state)
    if status is not None:
      query = query.where(Ticket.public_status == status)
    if category is not None:
      query = query.where(Ticket.category == category)
    if office_id is not None:
      query = query.where(Ticket.office_id == office_id)
    if creator_user_id is not None:
      query = query.where(Ticket.creator_user_id == creator_user_id)
    if primary_officer_id is not None:
      query = query.where(Ticket.primary_officer_id == primary_officer_id)
    if current_assignee_id is not None:
      query = query.where(Ticket.current_assignee_id == current_assignee_id)
    if created_from is not None:
      query = query.where(Ticket.created_at >= created_from)
    if created_to is not None:
      query = query.where(Ticket.created_at <= created_to)
    if updated_from is not None:
      query = query.where(Ticket.updated_at >= updated_from)
    if updated_to is not None:
      query = query.where(Ticket.updated_at <= updated_to)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=TicketProjectionRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Ticket.id,
      unique=True,
    )
