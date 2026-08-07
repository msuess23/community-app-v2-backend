import asyncio
import os
import uuid

import pytest

from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.ticket.domain import TicketCategory
from src.ticket.repositories.event import TicketEventRepository
from src.ticket.repositories.ticket import TicketProjectionRepository
from src.ticket.schemas import TicketCreateRequest, TicketUpdateRequest
from src.ticket.services.event_store import TicketEventStore
from src.ticket.services.ticket_commands import TicketCommandService
from src.user.models import Role, User

# Import every model before metadata.create_all is called.
import src.address.models  # noqa: F401,E402
import src.auth.models  # noqa: F401,E402
import src.office.models  # noqa: F401,E402
import src.ticket.models  # noqa: F401,E402


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


@pytest.mark.asyncio
async def test_concurrent_ticket_commands_keep_event_sequence_and_projection_consistent():
  """Verify row locking and deterministic replay against real PostgreSQL."""

  from src.core.config import settings

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  citizen = User(
    id=uuid.uuid4(),
    email="ticket.concurrency@example.com",
    hashed_password=get_password_hash("password123"),
    first_name="Concurrent",
    last_name="Citizen",
    role=Role.CITIZEN,
    is_active=True,
  )

  try:
    async with AsyncSessionLocal() as db:
      db.add(citizen)
      await db.flush()
      created = await TicketCommandService.create_ticket(
        db,
        TicketCreateRequest(
          title="Concurrent update test",
          category=TicketCategory.INFRASTRUCTURE,
        ),
        citizen,
      )
      ticket_id = created.id
      await db.commit()

    async def update_description(description: str) -> None:
      async with AsyncSessionLocal() as session:
        await TicketCommandService.update_ticket(
          session,
          ticket_id,
          TicketUpdateRequest(description=description),
          citizen,
        )
        await session.commit()

    await asyncio.gather(
      update_description("First concurrent value"),
      update_description("Second concurrent value"),
    )

    async with AsyncSessionLocal() as db:
      ticket = await TicketProjectionRepository.get_by_id(db, ticket_id)
      events = await TicketEventRepository.get_events(db, ticket_id)
      assert ticket is not None
      assert ticket.version == 3
      assert [event.sequence_number for event in events] == [1, 2, 3]
      rebuilt = await TicketEventStore.rebuild(db, ticket_id)
      assert rebuilt == TicketEventStore.state_from_ticket(ticket)
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
