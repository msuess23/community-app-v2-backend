"""Destructive PostgreSQL coverage for the complete idempotent seed catalog."""

import os

import pytest
from sqlalchemy import func, select

import src.models  # noqa: F401
from scripts.seed.run_seed import seed_database
from scripts.seed.seed_appointments import APPOINTMENT_SEED_KEYS
from scripts.seed.seed_infos import INFO_SEED_TITLES
from scripts.seed.seed_tickets import TICKET_SEED_TITLES
from src.appointment.domain import AppointmentStatus
from src.appointment.models import (
  Appointment,
  AppointmentDocument,
  AppointmentEvent,
  AppointmentSlot,
)
from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.info.models import Info, InfoImage, InfoStatus, InfoStatusEntry
from src.ticket.models import Ticket, TicketEvent, TicketImage


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


async def _reset_database() -> None:
  """Replace every mapped table with a clean test schema."""

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)


async def _catalog_snapshot() -> dict[str, object]:
  """Return stable counts and lifecycle sets for the seeded domain catalog."""

  async with AsyncSessionLocal() as db:
    scalar_counts = {
      "tickets": select(func.count()).select_from(Ticket).where(
        Ticket.title.in_(TICKET_SEED_TITLES)
      ),
      "ticket_events": select(func.count()).select_from(TicketEvent),
      "ticket_images": select(func.count()).select_from(TicketImage),
      "infos": select(func.count()).select_from(Info).where(
        Info.title.in_(INFO_SEED_TITLES)
      ),
      "info_status_entries": select(func.count()).select_from(InfoStatusEntry),
      "info_images": select(func.count()).select_from(InfoImage),
      "appointments": select(func.count()).select_from(Appointment),
      "appointment_events": select(func.count()).select_from(AppointmentEvent),
      "appointment_documents": select(func.count()).select_from(AppointmentDocument),
      "appointment_slots": select(func.count()).select_from(AppointmentSlot),
    }
    counts = {
      name: int((await db.execute(statement)).scalar_one())
      for name, statement in scalar_counts.items()
    }
    info_statuses = set(
      (await db.execute(select(Info.current_status).distinct())).scalars().all()
    )
    appointment_statuses = set(
      (await db.execute(select(Appointment.status).distinct())).scalars().all()
    )
    ticket_event_types = set(
      (await db.execute(select(TicketEvent.event_type).distinct())).scalars().all()
    )
    appointment_event_types = set(
      (await db.execute(select(AppointmentEvent.event_type).distinct())).scalars().all()
    )
    return {
      **counts,
      "info_statuses": info_statuses,
      "appointment_statuses": appointment_statuses,
      "ticket_event_types": ticket_event_types,
      "appointment_event_types": appointment_event_types,
    }


@pytest.mark.asyncio
async def test_complete_seed_catalog_is_varied_and_idempotent(
  monkeypatch,
  tmp_path,
) -> None:
  """Seed every domain twice without duplicating rows, events, or files."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "ENVIRONMENT", "test")
  monkeypatch.setattr(settings, "SEED_DEFAULT_PASSWORD", "password123")
  monkeypatch.setattr(settings, "TICKET_MEDIA_ROOT", str(tmp_path / "ticket-media"))
  monkeypatch.setattr(settings, "INFO_MEDIA_ROOT", str(tmp_path / "info-media"))
  monkeypatch.setattr(
    settings,
    "APPOINTMENT_DOCUMENT_ROOT",
    str(tmp_path / "appointment-documents"),
  )
  await _reset_database()

  try:
    await seed_database()
    first = await _catalog_snapshot()
    first_files = sorted(
      path.relative_to(tmp_path).as_posix()
      for path in tmp_path.rglob("*")
      if path.is_file()
    )

    await seed_database()
    second = await _catalog_snapshot()
    second_files = sorted(
      path.relative_to(tmp_path).as_posix()
      for path in tmp_path.rglob("*")
      if path.is_file()
    )

    assert first == second
    assert first_files == second_files
    assert first["tickets"] == len(TICKET_SEED_TITLES)
    assert first["infos"] == len(INFO_SEED_TITLES)
    assert first["appointments"] == len(APPOINTMENT_SEED_KEYS)
    assert first["ticket_events"] >= 40
    assert first["appointment_events"] >= 14
    assert first["ticket_images"] == 2
    assert first["info_images"] == 4
    assert first["appointment_documents"] == 4
    assert first["appointment_slots"] >= 9
    assert first["info_statuses"] == set(InfoStatus)
    assert first["appointment_statuses"] == set(AppointmentStatus)
    assert len(first["ticket_event_types"]) >= 12
    assert len(first["appointment_event_types"]) == 6
    assert len(first_files) == 10
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
