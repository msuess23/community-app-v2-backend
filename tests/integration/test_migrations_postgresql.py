from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["alembic", *args],
    cwd=PROJECT_ROOT,
    env=os.environ.copy(),
    check=True,
    capture_output=True,
    text=True,
  )


def test_postgresql_base_head_roundtrip_and_autogenerate_clean() -> None:
  if os.getenv("RUN_POSTGRES_TESTS") != "1":
    pytest.skip("set RUN_POSTGRES_TESTS=1 with a disposable PostgreSQL database")

  _run_alembic("upgrade", "head")
  _run_alembic("check")
  _run_alembic("downgrade", "base")
  _run_alembic("upgrade", "head")
  result = _run_alembic("check")

  assert "No new upgrade operations detected" in result.stdout
