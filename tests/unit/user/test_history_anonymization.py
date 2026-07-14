from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.constants import SYSTEM_USER_ID
from src.user.models import Role, UserHistory
from src.user.persistence import UserPersistence


@pytest.mark.asyncio
async def test_deep_anonymization_records_actor_time_and_reason() -> None:
  db = AsyncMock()
  result = AsyncMock()
  result.rowcount = 3
  db.execute.return_value = result
  cutoff = datetime.now(timezone.utc) - timedelta(days=180)

  count = await UserPersistence.bulk_anonymize_history(
    db,
    [Role.CITIZEN],
    cutoff,
  )

  assert count == 3
  statement = db.execute.await_args.args[0]
  values = statement.compile().params
  assert values["first_name"] == "gelöschter"
  assert values["last_name"] == "Nutzer"
  assert values["email"] == "deleted@local.com"
  assert values["anonymized_by_user_id"] == SYSTEM_USER_ID
  assert values["anonymization_reason"] == "Retention period expired"
  assert values["anonymized_at"].tzinfo is not None


def test_user_history_model_contains_redaction_audit_columns() -> None:
  columns = UserHistory.__table__.columns

  assert "anonymized_at" in columns
  assert "anonymized_by_user_id" in columns
  assert "anonymization_reason" in columns
