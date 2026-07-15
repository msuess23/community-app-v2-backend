import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.core.exceptions import ConflictException
from src.office.audit import build_address_snapshot, build_office_history
from src.office.models import Office
from src.office.schemas import OfficeCreate, OfficeUpdate
from src.office.service import OfficeService
from src.user.repository import UserRepository


def test_office_name_is_normalized() -> None:
  payload = OfficeCreate(name="  Bürgeramt\t Nord  ")
  assert payload.name == "Bürgeramt Nord"


def test_change_reason_is_required_for_office_updates() -> None:
  with pytest.raises(ValidationError):
    OfficeUpdate(description="Changed")


def test_address_history_snapshot_is_structured_and_complete() -> None:
  address = SimpleNamespace(
    id=uuid.uuid4(),
    street="Rathausplatz",
    house_number="1",
    zip_code="95028",
    city="Hof",
    latitude=50.32,
    longitude=11.92,
  )

  snapshot = build_address_snapshot(address)

  assert snapshot == {
    "id": str(address.id),
    "street": "Rathausplatz",
    "house_number": "1",
    "zip_code": "95028",
    "city": "Hof",
    "latitude": 50.32,
    "longitude": 11.92,
  }


def test_office_history_snapshot_contains_lifecycle() -> None:
  now = datetime.now(timezone.utc)
  version_start = now.replace(microsecond=0)
  office = Office(
    id=uuid.uuid4(),
    name="Bauamt",
    services=["Baugenehmigung"],
    opening_hours={"monday": "08:00-12:00"},
    is_active=False,
    deactivated_at=now,
    created_at=version_start,
    updated_at=version_start,
  )

  snapshot = build_office_history(
    office,
    actor_id=uuid.uuid4(),
    change_reason="Office deactivated",
    valid_to=now,
  )

  assert snapshot.is_active is False
  assert snapshot.deactivated_at == now
  assert snapshot.services == ["Baugenehmigung"]
  assert snapshot.opening_hours == {"monday": "08:00-12:00"}
  assert snapshot.valid_from == version_start
  assert snapshot.valid_to == now


@pytest.mark.asyncio
async def test_office_with_active_users_cannot_be_deactivated(monkeypatch) -> None:
  office = Office(id=uuid.uuid4(), name="Bauamt", is_active=True)
  monkeypatch.setattr(
    OfficeService,
    "_get_locked_office",
    AsyncMock(return_value=office),
  )
  monkeypatch.setattr(
    UserRepository,
    "has_active_users_in_office",
    AsyncMock(return_value=True),
  )

  with pytest.raises(ConflictException) as raised:
    await OfficeService.deactivate_office(
      AsyncMock(),
      office.id,
      uuid.uuid4(),
      change_reason="Organizational change",
    )

  assert raised.value.error_code == "OFFICE_HAS_ACTIVE_USERS"
  assert office.is_active is True
