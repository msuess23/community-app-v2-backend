"""SQLAlchemy repositories for slots, appointment projections and events."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Mapping

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from src.appointment.domain import (
  AppointmentEventType,
  AppointmentSlotSortField,
  AppointmentSlotStatus,
  AppointmentSortField,
  AppointmentStatus,
)
from src.appointment.models import (
  Appointment,
  AppointmentDocument,
  AppointmentEvent,
  AppointmentSlot,
)
from src.core.filters import SortOrder, apply_search_filter
from src.core.pagination import execute_page
from src.office.models import Office
from src.ticket.models import Ticket
from src.user.models import User


class AppointmentSlotRepository:
  """Persist and query office capacity slots."""

  SORT_COLUMNS: ClassVar[
    Mapping[AppointmentSlotSortField, InstrumentedAttribute[Any]]
  ] = {
    AppointmentSlotSortField.STARTS_AT: AppointmentSlot.starts_at,
    AppointmentSlotSortField.CREATED_AT: AppointmentSlot.created_at,
    AppointmentSlotSortField.STATUS: AppointmentSlot.status,
  }

  @staticmethod
  async def get_office_for_update(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> Office | None:
    """Lock one office to serialize overlap-sensitive slot batches."""

    result = await db.execute(
      select(Office).where(Office.id == office_id).with_for_update()
    )
    return result.scalar_one_or_none()

  @staticmethod
  async def get_by_id(
    db: AsyncSession,
    slot_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> AppointmentSlot | None:
    """Load one slot, optionally locking it for a booking command."""

    query = select(AppointmentSlot).where(AppointmentSlot.id == slot_id)
    if for_update:
      query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()

  @staticmethod
  async def get_many_for_update(
    db: AsyncSession,
    slot_ids: list[uuid.UUID],
  ) -> dict[uuid.UUID, AppointmentSlot]:
    """Lock several slots in stable UUID order to avoid lock inversion."""

    ordered_ids = sorted(set(slot_ids), key=str)
    result = await db.execute(
      select(AppointmentSlot)
      .where(AppointmentSlot.id.in_(ordered_ids))
      .order_by(AppointmentSlot.id.asc())
      .with_for_update()
    )
    return {slot.id: slot for slot in result.scalars().all()}

  @staticmethod
  async def get_page(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    page: int,
    size: int,
    status: AppointmentSlotStatus | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    public_only: bool,
    sort_by: AppointmentSlotSortField,
    order: SortOrder,
  ) -> tuple[list[AppointmentSlot], int]:
    """Return a stable slot page for public discovery or office management."""

    query = select(AppointmentSlot).where(AppointmentSlot.office_id == office_id)
    if public_only:
      query = query.where(
        AppointmentSlot.status == AppointmentSlotStatus.AVAILABLE,
        AppointmentSlot.starts_at >= datetime.now(timezone.utc),
      )
    elif status is not None:
      query = query.where(AppointmentSlot.status == status)

    if starts_from is not None:
      query = query.where(AppointmentSlot.starts_at >= starts_from)
    if starts_to is not None:
      query = query.where(AppointmentSlot.starts_at <= starts_to)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=AppointmentSlotRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=AppointmentSlot.id,
    )

  @staticmethod
  async def has_overlap(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
  ) -> bool:
    """Return whether an available or booked slot overlaps one interval."""

    result = await db.execute(
      select(AppointmentSlot.id)
      .where(
        AppointmentSlot.office_id == office_id,
        AppointmentSlot.status.in_(
          {AppointmentSlotStatus.AVAILABLE, AppointmentSlotStatus.BOOKED}
        ),
        AppointmentSlot.starts_at < ends_at,
        AppointmentSlot.ends_at > starts_at,
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None

  @staticmethod
  async def has_future_available_slots(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> bool:
    """Return whether an office still offers future bookable capacity."""

    result = await db.execute(
      select(AppointmentSlot.id)
      .where(
        AppointmentSlot.office_id == office_id,
        AppointmentSlot.status == AppointmentSlotStatus.AVAILABLE,
        AppointmentSlot.starts_at > datetime.now(timezone.utc),
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None

  @staticmethod
  def add_all(db: AsyncSession, slots: list[AppointmentSlot]) -> None:
    """Stage a validated slot batch."""

    db.add_all(slots)


class AppointmentRepository:
  """Persist and query current appointment projections."""

  SORT_COLUMNS: ClassVar[
    Mapping[AppointmentSortField, InstrumentedAttribute[Any]]
  ] = {
    AppointmentSortField.STARTS_AT: Appointment.starts_at,
    AppointmentSortField.CREATED_AT: Appointment.created_at,
    AppointmentSortField.STATUS: Appointment.status,
  }

  @staticmethod
  def _detail_query():
    """Build the eager-loading query shared by appointment detail reads."""

    return select(Appointment).options(
      selectinload(Appointment.office),
      selectinload(Appointment.citizen),
      selectinload(Appointment.ticket),
      selectinload(Appointment.current_slot),
    )

  @staticmethod
  async def get_by_id(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> Appointment | None:
    """Load one current appointment projection."""

    query = AppointmentRepository._detail_query().where(
      Appointment.id == appointment_id
    )
    if for_update:
      query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()

  @staticmethod
  async def get_citizen_page(
    db: AsyncSession,
    *,
    citizen_id: uuid.UUID,
    page: int,
    size: int,
    status: AppointmentStatus | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    search: str | None,
    sort_by: AppointmentSortField,
    order: SortOrder,
  ) -> tuple[list[Appointment], int]:
    """Return appointments owned by one citizen."""

    query = (
      AppointmentRepository._detail_query()
      .join(Office, Appointment.office_id == Office.id)
      .where(Appointment.citizen_id == citizen_id)
    )
    query = apply_search_filter(query, search, Appointment.reason, Office.name)
    if status is not None:
      query = query.where(Appointment.status == status)
    if starts_from is not None:
      query = query.where(Appointment.starts_at >= starts_from)
    if starts_to is not None:
      query = query.where(Appointment.starts_at <= starts_to)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=AppointmentRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Appointment.id,
      unique=True,
    )

  @staticmethod
  async def get_internal_page(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
    page: int,
    size: int,
    citizen_id: uuid.UUID | None,
    ticket_id: uuid.UUID | None,
    status: AppointmentStatus | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
    created_from: datetime | None,
    created_to: datetime | None,
    search: str | None,
    sort_by: AppointmentSortField,
    order: SortOrder,
  ) -> tuple[list[Appointment], int]:
    """Return the office-scoped authority appointment page."""

    query = (
      AppointmentRepository._detail_query()
      .join(Office, Appointment.office_id == Office.id)
      .join(User, Appointment.citizen_id == User.id)
      .outerjoin(Ticket, Appointment.ticket_id == Ticket.id)
      .where(Appointment.office_id == office_id)
    )
    query = apply_search_filter(
      query,
      search,
      Appointment.reason,
      User.first_name,
      User.last_name,
      User.email,
      Ticket.title,
    )
    if citizen_id is not None:
      query = query.where(Appointment.citizen_id == citizen_id)
    if ticket_id is not None:
      query = query.where(Appointment.ticket_id == ticket_id)
    if status is not None:
      query = query.where(Appointment.status == status)
    if starts_from is not None:
      query = query.where(Appointment.starts_at >= starts_from)
    if starts_to is not None:
      query = query.where(Appointment.starts_at <= starts_to)
    if created_from is not None:
      query = query.where(Appointment.created_at >= created_from)
    if created_to is not None:
      query = query.where(Appointment.created_at <= created_to)

    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=AppointmentRepository.SORT_COLUMNS[sort_by],
      order=order,
      tie_breaker=Appointment.id,
      unique=True,
    )

  @staticmethod
  async def get_internal_filter_reference_ids(
    db: AsyncSession,
    *,
    office_id: uuid.UUID,
  ) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Return citizen and ticket identifiers from the complete office scope."""

    result = await db.execute(
      select(Appointment.citizen_id, Appointment.ticket_id).where(
        Appointment.office_id == office_id
      )
    )
    citizen_ids: set[uuid.UUID] = set()
    ticket_ids: set[uuid.UUID] = set()
    for citizen_id, ticket_id in result.all():
      citizen_ids.add(citizen_id)
      if ticket_id is not None:
        ticket_ids.add(ticket_id)
    return citizen_ids, ticket_ids

  @staticmethod
  async def get_tickets_by_ids(
    db: AsyncSession,
    ticket_ids: set[uuid.UUID],
  ) -> list[Ticket]:
    """Batch-load linked tickets used by internal filter options."""

    if not ticket_ids:
      return []
    result = await db.execute(select(Ticket).where(Ticket.id.in_(ticket_ids)))
    return list(result.scalars().all())

  @staticmethod
  async def has_scheduled_for_citizen(
    db: AsyncSession,
    citizen_id: uuid.UUID,
  ) -> bool:
    """Return whether a citizen owns at least one scheduled appointment."""

    result = await db.execute(
      select(Appointment.id)
      .where(
        Appointment.citizen_id == citizen_id,
        Appointment.status == AppointmentStatus.SCHEDULED,
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None

  @staticmethod
  async def has_scheduled_for_office(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> bool:
    """Return whether an office owns at least one scheduled appointment."""

    result = await db.execute(
      select(Appointment.id)
      .where(
        Appointment.office_id == office_id,
        Appointment.status == AppointmentStatus.SCHEDULED,
      )
      .limit(1)
    )
    return result.scalar_one_or_none() is not None

  @staticmethod
  def add(db: AsyncSession, appointment: Appointment) -> None:
    """Stage one appointment projection."""

    db.add(appointment)


class AppointmentEventRepository:
  """Persist and read ordered appointment event streams."""

  @staticmethod
  def add(db: AsyncSession, event: AppointmentEvent) -> None:
    """Stage one immutable aggregate event."""

    db.add(event)

  @staticmethod
  async def get_last_sequence_number(
    db: AsyncSession,
    appointment_id: uuid.UUID,
  ) -> int:
    """Return the persisted stream version for projection verification."""

    result = await db.execute(
      select(func.coalesce(func.max(AppointmentEvent.sequence_number), 0)).where(
        AppointmentEvent.appointment_id == appointment_id
      )
    )
    return int(result.scalar_one())

  @staticmethod
  async def get_event_page(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    *,
    page: int,
    size: int,
    citizen_visible_only: bool = False,
  ) -> tuple[list[AppointmentEvent], int]:
    """Return a newest-first event page with optional citizen filtering."""

    query = select(AppointmentEvent).where(
      AppointmentEvent.appointment_id == appointment_id
    )
    if citizen_visible_only:
      query = query.where(
        or_(
          AppointmentEvent.event_type != AppointmentEventType.DOCUMENT_VERSION_ADDED,
          AppointmentEvent.payload["visible_to_citizen"].as_boolean().is_(True),
        )
      )
    else:
      query = query.options(selectinload(AppointmentEvent.actor))
    return await execute_page(
      db,
      query,
      page=page,
      size=size,
      sort_column=AppointmentEvent.sequence_number,
      order=SortOrder.DESC,
      tie_breaker=AppointmentEvent.id,
    )

  @staticmethod
  async def get_events(
    db: AsyncSession,
    appointment_id: uuid.UUID,
  ) -> list[AppointmentEvent]:
    """Return a complete event stream in sequence order."""

    result = await db.execute(
      select(AppointmentEvent)
      .where(AppointmentEvent.appointment_id == appointment_id)
      .order_by(AppointmentEvent.sequence_number.asc())
    )
    return list(result.scalars().all())


class AppointmentDocumentRepository:
  """Persist and read immutable versions of appointment documents."""

  @staticmethod
  def add(db: AsyncSession, document: AppointmentDocument) -> None:
    """Stage one new immutable document version."""

    db.add(document)

  @staticmethod
  async def get_current_documents(
    db: AsyncSession,
    appointment_id: uuid.UUID,
    *,
    visible_only: bool = False,
  ) -> list[AppointmentDocument]:
    """Return current document versions in deterministic upload order."""

    query = select(AppointmentDocument).where(
      AppointmentDocument.appointment_id == appointment_id,
      AppointmentDocument.is_current.is_(True),
    )
    if visible_only:
      query = query.where(AppointmentDocument.visible_to_citizen.is_(True))
    result = await db.execute(
      query.order_by(
        AppointmentDocument.uploaded_at.asc(),
        AppointmentDocument.id.asc(),
      )
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_current_for_group(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    document_group_id: uuid.UUID,
    for_update: bool = False,
  ) -> AppointmentDocument | None:
    """Load the current version of one document group."""

    query = select(AppointmentDocument).where(
      AppointmentDocument.appointment_id == appointment_id,
      AppointmentDocument.document_group_id == document_group_id,
      AppointmentDocument.is_current.is_(True),
    )
    if for_update:
      query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()

  @staticmethod
  async def get_versions(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    document_group_id: uuid.UUID,
  ) -> list[AppointmentDocument]:
    """Return every retained version of one document group."""

    result = await db.execute(
      select(AppointmentDocument)
      .where(
        AppointmentDocument.appointment_id == appointment_id,
        AppointmentDocument.document_group_id == document_group_id,
      )
      .order_by(AppointmentDocument.version_number.desc())
    )
    return list(result.scalars().all())

  @staticmethod
  async def get_by_id(
    db: AsyncSession,
    *,
    appointment_id: uuid.UUID,
    document_version_id: uuid.UUID,
  ) -> AppointmentDocument | None:
    """Load one concrete document version within an appointment."""

    result = await db.execute(
      select(AppointmentDocument).where(
        AppointmentDocument.id == document_version_id,
        AppointmentDocument.appointment_id == appointment_id,
      )
    )
    return result.scalar_one_or_none()
