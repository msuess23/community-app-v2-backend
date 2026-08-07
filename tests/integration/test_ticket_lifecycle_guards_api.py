"""Destructive PostgreSQL checks for cross-domain ticket lifecycle guards."""

import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from src.core.config import settings
from src.core.database import AsyncSessionLocal, Base, engine
from src.core.security import get_password_hash
from src.main import app, lifespan
from src.office.models import Office
from src.ticket.domain import (
  TicketCategory,
  TicketStatus,
  TicketVisibility,
  TicketWorkflowState,
)
from src.ticket.models import Ticket
from src.user.models import Role, User

# Import every active model before metadata.create_all is called.
import src.address.models  # noqa: F401,E402
import src.auth.models  # noqa: F401,E402
import src.ticket.models  # noqa: F401,E402


pytestmark = pytest.mark.skipif(
  os.getenv("RUN_POSTGRES_TESTS") != "1",
  reason="Set RUN_POSTGRES_TESTS=1 to run destructive PostgreSQL integration tests",
)


@pytest.mark.asyncio
async def test_active_ticket_blocks_user_and_office_deactivation(monkeypatch) -> None:
  """Verify API-level guards and the reduced public ticket representation."""

  if "test" not in settings.POSTGRES_DB.lower():
    pytest.fail("PostgreSQL integration tests require a disposable test database")

  monkeypatch.setattr(settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)

  async with engine.begin() as connection:
    await connection.run_sync(Base.metadata.drop_all)
    await connection.run_sync(Base.metadata.create_all)

  admin_id = uuid.uuid4()
  citizen_id = uuid.uuid4()
  office_id = uuid.uuid4()
  ticket_id = uuid.uuid4()
  now = datetime.now(timezone.utc)

  try:
    async with AsyncSessionLocal() as db:
      db.add_all(
        [
          User(
            id=admin_id,
            email="guard.admin@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Guard",
            last_name="Admin",
            role=Role.ADMIN,
            is_active=True,
          ),
          User(
            id=citizen_id,
            email="guard.citizen@example.com",
            hashed_password=get_password_hash("password123"),
            first_name="Guard",
            last_name="Citizen",
            role=Role.CITIZEN,
            is_active=True,
          ),
          Office(
            id=office_id,
            name="Guard Office",
            services=[],
            opening_hours={},
            is_active=True,
          ),
          Ticket(
            id=ticket_id,
            title="Guarded ticket",
            category=TicketCategory.INFRASTRUCTURE,
            creator_user_id=citizen_id,
            office_id=office_id,
            visibility=TicketVisibility.PUBLIC,
            public_status=TicketStatus.IN_PROGRESS,
            workflow_state=TicketWorkflowState.AWAITING_PRIMARY_ASSIGNMENT,
            version=1,
            created_at=now,
            updated_at=now,
          ),
        ]
      )
      await db.commit()

    async with lifespan(app):
      transport = httpx.ASGITransport(app=app)
      async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
      ) as client:
        login = await client.post(
          "/api/v1/auth/login",
          data={"username": "guard.admin@example.com", "password": "password123"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        user_delete = await client.request(
          "DELETE",
          f"/api/v1/users/{citizen_id}",
          headers=headers,
          json={"change_reason": "Should remain active"},
        )
        assert user_delete.status_code == 409
        assert user_delete.json()["error_code"] == "USER_HAS_ACTIVE_TICKETS"

        office_delete = await client.request(
          "DELETE",
          f"/api/v1/offices/{office_id}",
          headers=headers,
          json={"change_reason": "Should remain active"},
        )
        assert office_delete.status_code == 409
        assert office_delete.json()["error_code"] == "OFFICE_HAS_ACTIVE_TICKETS"

        public_ticket = await client.get(f"/api/v1/tickets/{ticket_id}")
        assert public_ticket.status_code == 200
        assert "creator_user_id" not in public_ticket.json()
  finally:
    async with engine.begin() as connection:
      await connection.run_sync(Base.metadata.drop_all)
