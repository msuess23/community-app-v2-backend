from unittest.mock import AsyncMock, MagicMock

import pytest

import src.main as main_module


@pytest.mark.asyncio
async def test_lifespan_runs_enabled_startup_tasks_and_cleans_up(monkeypatch):
  seed_database = AsyncMock()
  setup_scheduler = MagicMock()
  shutdown_scheduler = MagicMock()
  fake_engine = MagicMock()
  fake_engine.dispose = AsyncMock()

  monkeypatch.setattr(main_module.settings, "RUN_SEED_ON_STARTUP", True)
  monkeypatch.setattr(main_module.settings, "ENABLE_SCHEDULER", True)
  monkeypatch.setattr(main_module, "seed_database", seed_database)
  monkeypatch.setattr(main_module, "setup_scheduler", setup_scheduler)
  monkeypatch.setattr(main_module, "shutdown_scheduler", shutdown_scheduler)
  monkeypatch.setattr(main_module, "engine", fake_engine)

  async with main_module.lifespan(MagicMock()):
    seed_database.assert_awaited_once()
    setup_scheduler.assert_called_once()

  shutdown_scheduler.assert_called_once()
  fake_engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_skips_disabled_optional_tasks(monkeypatch):
  seed_database = AsyncMock()
  setup_scheduler = MagicMock()
  shutdown_scheduler = MagicMock()
  fake_engine = MagicMock()
  fake_engine.dispose = AsyncMock()

  monkeypatch.setattr(main_module.settings, "RUN_SEED_ON_STARTUP", False)
  monkeypatch.setattr(main_module.settings, "ENABLE_SCHEDULER", False)
  monkeypatch.setattr(main_module, "seed_database", seed_database)
  monkeypatch.setattr(main_module, "setup_scheduler", setup_scheduler)
  monkeypatch.setattr(main_module, "shutdown_scheduler", shutdown_scheduler)
  monkeypatch.setattr(main_module, "engine", fake_engine)

  async with main_module.lifespan(MagicMock()):
    pass

  seed_database.assert_not_awaited()
  setup_scheduler.assert_not_called()
  shutdown_scheduler.assert_not_called()
  fake_engine.dispose.assert_awaited_once()
