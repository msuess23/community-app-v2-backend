from unittest.mock import AsyncMock, MagicMock

import pytest

import src.core.scheduler as scheduler_module


class SessionContext:
  def __init__(self, session):
    self.session = session

  async def __aenter__(self):
    return self.session

  async def __aexit__(self, exc_type, exc, tb):
    return False


@pytest.mark.asyncio
async def test_anonymization_job_uses_configured_retention_and_commits(monkeypatch):
  session = MagicMock()
  session.commit = AsyncMock()
  session.rollback = AsyncMock()
  anonymize = AsyncMock()

  monkeypatch.setattr(
    scheduler_module,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )
  monkeypatch.setattr(
    scheduler_module.UserService,
    "run_deep_anonymization",
    anonymize,
  )
  monkeypatch.setattr(
    scheduler_module.settings,
    "CITIZEN_HISTORY_RETENTION_DAYS",
    90,
  )

  await scheduler_module.anonymization_cron_task()

  anonymize.assert_awaited_once_with(session, retention_days=90)
  session.commit.assert_awaited_once()
  session.rollback.assert_not_awaited()
