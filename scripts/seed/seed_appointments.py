"""Seed appointment slots, event streams, and versioned PDF documents."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed.context import SeedContext
from scripts.seed.media_factory import pdf_upload
from scripts.seed.seed_tickets import TICKET_SEED_TITLES
from src.appointment.document_service import AppointmentDocumentService
from src.appointment.domain import (
  AppointmentBookedPayload,
  AppointmentCancelledPayload,
  AppointmentCompletedPayload,
  AppointmentDocumentType,
  AppointmentEventType,
  AppointmentMarkedNoShowPayload,
  AppointmentRescheduledPayload,
  AppointmentSlotStatus,
)
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment, AppointmentSlot
from src.appointment.repository import AppointmentSlotRepository
from src.appointment.schemas import AppointmentDocumentResponse
from src.ticket.models import Ticket
from src.user.models import User

logger = logging.getLogger(__name__)

SEED_NAMESPACE = uuid.UUID("63e91b6b-9d53-4b49-a93c-b50cf6c27dd8")
APPOINTMENT_SEED_KEYS = (
  "scheduled-bauamt",
  "rescheduled-bauamt",
  "cancelled-buergeramt",
  "completed-bauamt",
  "no-show-buergeramt",
  "ticket-linked-bauamt",
)


def _seed_uuid(kind: str, key: str) -> uuid.UUID:
  """Return a stable UUID for one deterministic appointment seed object."""

  return uuid.uuid5(SEED_NAMESPACE, f"{kind}:{key}")


async def _get_appointment(
  db: AsyncSession,
  key: str,
) -> Appointment | None:
  """Load one appointment scenario by its deterministic identifier."""

  result = await db.execute(
    select(Appointment).where(Appointment.id == _seed_uuid("appointment", key))
  )
  return result.scalar_one_or_none()


async def _get_ticket(db: AsyncSession, title: str) -> Ticket | None:
  """Load a seeded ticket used by a linked appointment scenario."""

  result = await db.execute(select(Ticket).where(Ticket.title == title).limit(1))
  return result.scalar_one_or_none()


async def _ensure_slot(
  db: AsyncSession,
  *,
  key: str,
  office_id: uuid.UUID,
  starts_at: datetime,
  ends_at: datetime,
  status: AppointmentSlotStatus,
  created_by: User,
) -> AppointmentSlot:
  """Create or load one deterministic appointment slot."""

  slot_id = _seed_uuid("slot", key)
  existing = await AppointmentSlotRepository.get_by_id(db, slot_id)
  if existing is not None:
    return existing

  slot = AppointmentSlot(
    id=slot_id,
    office_id=office_id,
    starts_at=starts_at,
    ends_at=ends_at,
    status=status,
    created_by_user_id=created_by.id,
  )
  AppointmentSlotRepository.add_all(db, [slot])
  await db.flush()
  return slot


async def _create_booking(
  db: AsyncSession,
  *,
  key: str,
  slot: AppointmentSlot,
  citizen: User,
  reason: str,
  ticket_id: uuid.UUID | None = None,
  occurred_at: datetime,
) -> Appointment:
  """Create one appointment projection from its initial booking event."""

  appointment, _event = await AppointmentEventStore.create(
    db,
    appointment_id=_seed_uuid("appointment", key),
    actor_user_id=citizen.id,
    payload=AppointmentBookedPayload(
      slot_id=slot.id,
      office_id=slot.office_id,
      citizen_id=citizen.id,
      ticket_id=ticket_id,
      reason=reason,
      starts_at=slot.starts_at,
      ends_at=slot.ends_at,
    ),
    occurred_at=occurred_at,
  )
  slot.status = AppointmentSlotStatus.BOOKED
  await db.flush()
  return appointment


async def _upload_document(
  db: AsyncSession,
  *,
  appointment: Appointment,
  actor: User,
  filename: str,
  title: str,
  document_type: AppointmentDocumentType,
  visible_to_citizen: bool,
  replace_document_group_id: uuid.UUID | None = None,
) -> AppointmentDocumentResponse:
  """Upload one generated PDF through the versioned document service."""

  upload = pdf_upload(filename, title=title)
  try:
    return await AppointmentDocumentService.upload_version(
      db,
      appointment_id=appointment.id,
      upload=upload,
      document_type=document_type,
      visible_to_citizen=visible_to_citizen,
      replace_document_group_id=replace_document_group_id,
      current_user=actor,
    )
  finally:
    await upload.close()


async def run_appointment_seeder(
  db: AsyncSession,
  context: SeedContext,
) -> None:
  """Seed slot states, appointment lifecycles, ticket links, and PDF versions."""

  logger.info("Seeding appointment scenarios")
  now = datetime.now(timezone.utc)
  anchor = now.replace(hour=9, minute=0, second=0, microsecond=0)
  bauamt = context.office("Bauamt")
  buergeramt = context.office("Bürgeramt")
  manager1 = context.user("manager1@bauamt.com")
  manager3 = context.user("manager3@buergeramt.com")
  citizen1 = context.user("citizen1@test.com")
  citizen2 = context.user("citizen2@test.com")
  citizen3 = context.user("citizen3@test.com")

  # Standalone capacity rows demonstrate public availability and deactivation.
  await _ensure_slot(
    db,
    key="available-bauamt",
    office_id=bauamt.id,
    starts_at=anchor + timedelta(days=14),
    ends_at=anchor + timedelta(days=14, minutes=30),
    status=AppointmentSlotStatus.AVAILABLE,
    created_by=manager1,
  )
  await _ensure_slot(
    db,
    key="inactive-buergeramt",
    office_id=buergeramt.id,
    starts_at=anchor + timedelta(days=15),
    ends_at=anchor + timedelta(days=15, minutes=45),
    status=AppointmentSlotStatus.INACTIVE,
    created_by=manager3,
  )

  if await _get_appointment(db, APPOINTMENT_SEED_KEYS[0]) is None:
    slot = await _ensure_slot(
      db,
      key="scheduled-bauamt",
      office_id=bauamt.id,
      starts_at=anchor + timedelta(days=5),
      ends_at=anchor + timedelta(days=5, minutes=30),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager1,
    )
    appointment = await _create_booking(
      db,
      key=APPOINTMENT_SEED_KEYS[0],
      slot=slot,
      citizen=citizen1,
      reason="Discuss a building-file inspection request.",
      occurred_at=now - timedelta(days=1),
    )
    confirmation = await _upload_document(
      db,
      appointment=appointment,
      actor=manager1,
      filename="appointment-confirmation-v1.pdf",
      title="Appointment confirmation version 1",
      document_type=AppointmentDocumentType.CONFIRMATION,
      visible_to_citizen=True,
    )
    await _upload_document(
      db,
      appointment=appointment,
      actor=manager1,
      filename="appointment-confirmation-v2.pdf",
      title="Appointment confirmation version 2",
      document_type=AppointmentDocumentType.CONFIRMATION,
      visible_to_citizen=True,
      replace_document_group_id=confirmation.document_group_id,
    )
    await _upload_document(
      db,
      appointment=appointment,
      actor=manager1,
      filename="internal-preparation-form.pdf",
      title="Internal preparation form",
      document_type=AppointmentDocumentType.FORM,
      visible_to_citizen=False,
    )
    logger.info("Created scheduled appointment with versioned documents")

  if await _get_appointment(db, APPOINTMENT_SEED_KEYS[1]) is None:
    previous = await _ensure_slot(
      db,
      key="rescheduled-bauamt-previous",
      office_id=bauamt.id,
      starts_at=anchor + timedelta(days=7),
      ends_at=anchor + timedelta(days=7, minutes=30),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager1,
    )
    target = await _ensure_slot(
      db,
      key="rescheduled-bauamt-target",
      office_id=bauamt.id,
      starts_at=anchor + timedelta(days=8),
      ends_at=anchor + timedelta(days=8, minutes=30),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager1,
    )
    appointment = await _create_booking(
      db,
      key=APPOINTMENT_SEED_KEYS[1],
      slot=previous,
      citizen=citizen2,
      reason="Clarify a construction-site access permit.",
      occurred_at=now - timedelta(days=3),
    )
    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=citizen2.id,
      event_type=AppointmentEventType.APPOINTMENT_RESCHEDULED,
      payload=AppointmentRescheduledPayload(
        previous_slot_id=previous.id,
        new_slot_id=target.id,
        previous_starts_at=previous.starts_at,
        previous_ends_at=previous.ends_at,
        new_starts_at=target.starts_at,
        new_ends_at=target.ends_at,
        reason="A conflicting work appointment required a later date.",
      ),
      occurred_at=now - timedelta(days=2),
    )
    previous.status = AppointmentSlotStatus.AVAILABLE
    target.status = AppointmentSlotStatus.BOOKED
    await db.flush()

  if await _get_appointment(db, APPOINTMENT_SEED_KEYS[2]) is None:
    slot = await _ensure_slot(
      db,
      key="cancelled-buergeramt",
      office_id=buergeramt.id,
      starts_at=anchor + timedelta(days=10),
      ends_at=anchor + timedelta(days=10, minutes=20),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager3,
    )
    appointment = await _create_booking(
      db,
      key=APPOINTMENT_SEED_KEYS[2],
      slot=slot,
      citizen=citizen3,
      reason="Collect a prepared identity document.",
      occurred_at=now - timedelta(days=2),
    )
    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=citizen3.id,
      event_type=AppointmentEventType.APPOINTMENT_CANCELLED,
      payload=AppointmentCancelledPayload(
        slot_id=slot.id,
        reason="The document can be delivered by post instead.",
      ),
      occurred_at=now - timedelta(days=1),
    )
    slot.status = AppointmentSlotStatus.AVAILABLE
    await db.flush()

  if await _get_appointment(db, APPOINTMENT_SEED_KEYS[3]) is None:
    slot = await _ensure_slot(
      db,
      key="completed-bauamt",
      office_id=bauamt.id,
      starts_at=anchor - timedelta(days=6),
      ends_at=anchor - timedelta(days=6) + timedelta(minutes=45),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager1,
    )
    appointment = await _create_booking(
      db,
      key=APPOINTMENT_SEED_KEYS[3],
      slot=slot,
      citizen=citizen1,
      reason="Review submitted site plans with the responsible office.",
      occurred_at=now - timedelta(days=12),
    )
    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=manager1.id,
      event_type=AppointmentEventType.APPOINTMENT_COMPLETED,
      payload=AppointmentCompletedPayload(
        comment="Documents were reviewed and follow-up tasks were explained."
      ),
      occurred_at=slot.ends_at + timedelta(minutes=5),
    )
    slot.status = AppointmentSlotStatus.CONSUMED
    await db.flush()
    await _upload_document(
      db,
      appointment=appointment,
      actor=manager1,
      filename="appointment-protocol.pdf",
      title="Internal appointment protocol",
      document_type=AppointmentDocumentType.PROTOCOL,
      visible_to_citizen=False,
    )

  if await _get_appointment(db, APPOINTMENT_SEED_KEYS[4]) is None:
    slot = await _ensure_slot(
      db,
      key="no-show-buergeramt",
      office_id=buergeramt.id,
      starts_at=anchor - timedelta(days=3),
      ends_at=anchor - timedelta(days=3) + timedelta(minutes=20),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager3,
    )
    appointment = await _create_booking(
      db,
      key=APPOINTMENT_SEED_KEYS[4],
      slot=slot,
      citizen=citizen2,
      reason="Verify residence registration documents.",
      occurred_at=now - timedelta(days=8),
    )
    await AppointmentEventStore.append(
      db,
      appointment,
      actor_user_id=manager3.id,
      event_type=AppointmentEventType.APPOINTMENT_MARKED_NO_SHOW,
      payload=AppointmentMarkedNoShowPayload(
        comment="The citizen did not arrive during the reserved interval."
      ),
      occurred_at=slot.ends_at + timedelta(minutes=10),
    )
    slot.status = AppointmentSlotStatus.CONSUMED
    await db.flush()

  if await _get_appointment(db, APPOINTMENT_SEED_KEYS[5]) is None:
    linked_ticket = await _get_ticket(db, TICKET_SEED_TITLES[8])
    if linked_ticket is None:
      raise RuntimeError("Required seeded ticket for appointment link is missing")
    slot = await _ensure_slot(
      db,
      key="ticket-linked-bauamt",
      office_id=bauamt.id,
      starts_at=anchor + timedelta(days=6, hours=2),
      ends_at=anchor + timedelta(days=6, hours=2, minutes=30),
      status=AppointmentSlotStatus.AVAILABLE,
      created_by=manager1,
    )
    await _create_booking(
      db,
      key=APPOINTMENT_SEED_KEYS[5],
      slot=slot,
      citizen=citizen3,
      reason="Discuss follow-up questions concerning the completed traffic-sign ticket.",
      ticket_id=linked_ticket.id,
      occurred_at=now - timedelta(hours=12),
    )

  logger.info("Appointment scenario seeding completed")
