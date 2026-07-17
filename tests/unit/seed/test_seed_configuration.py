from unittest.mock import AsyncMock

import pytest

import scripts.seed.run_seed as seed_module


@pytest.mark.asyncio
async def test_seeding_is_blocked_in_production(monkeypatch):
  monkeypatch.setattr(seed_module.settings, "ENVIRONMENT", "production")
  monkeypatch.setattr(seed_module.settings, "SEED_DEFAULT_PASSWORD", "password123")

  with pytest.raises(RuntimeError, match="disabled in production"):
    await seed_module.seed_database()


@pytest.mark.asyncio
async def test_seeding_requires_configured_password(monkeypatch):
  monkeypatch.setattr(seed_module.settings, "ENVIRONMENT", "development")
  monkeypatch.setattr(seed_module.settings, "SEED_DEFAULT_PASSWORD", None)

  with pytest.raises(RuntimeError, match="SEED_DEFAULT_PASSWORD"):
    await seed_module.seed_database()
