"""Verify ticket and appointment snapshot projections against their event streams."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import src.models  # noqa: F401
from src.appointment.event_store import AppointmentEventStore
from src.appointment.models import Appointment
from src.appointment.repository import AppointmentRepository
from src.core.database import AsyncSessionLocal
from src.ticket.models import Ticket
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.services.event_store import TicketEventStore


@dataclass(frozen=True)
class ProjectionMismatch:
  """Describe one aggregate whose snapshot differs from deterministic replay."""

  aggregate_type: str
  aggregate_id: UUID


async def find_projection_mismatches(db: AsyncSession) -> list[ProjectionMismatch]:
  """Return every ticket or appointment projection that differs from replay."""

  mismatches: list[ProjectionMismatch] = []
  ticket_ids = list((await db.execute(select(Ticket.id))).scalars().all())
  for ticket_id in ticket_ids:
    ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
    assert ticket is not None
    projection = TicketEventStore.state_from_ticket(ticket)
    replay = await TicketEventStore.rebuild(db, ticket_id)
    if projection != replay:
      mismatches.append(ProjectionMismatch("ticket", ticket_id))

  appointment_ids = list((await db.execute(select(Appointment.id))).scalars().all())
  for appointment_id in appointment_ids:
    appointment = await AppointmentRepository.get_by_id(db, appointment_id)
    assert appointment is not None
    projection = AppointmentEventStore.state_from_appointment(appointment)
    replay = await AppointmentEventStore.rebuild(db, appointment_id)
    if projection != replay:
      mismatches.append(ProjectionMismatch("appointment", appointment_id))

  return mismatches


async def main() -> None:
  """Exit successfully only when every event-sourced projection matches replay."""

  async with AsyncSessionLocal() as db:
    mismatches = await find_projection_mismatches(db)
  if mismatches:
    details = ", ".join(
      f"{item.aggregate_type}:{item.aggregate_id}" for item in mismatches
    )
    raise RuntimeError(f"Event projection verification failed: {details}")
  print("All ticket and appointment projections match their event streams.")


if __name__ == "__main__":
  asyncio.run(main())
