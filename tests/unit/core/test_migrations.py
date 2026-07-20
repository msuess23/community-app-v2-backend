import os
import subprocess
import sys


def _alembic_environment() -> dict[str, str]:
  return {
    **os.environ,
    "PROJECT_NAME": "Migration Test",
    "BASE_URL": "/api/v1",
    "SECRET_KEY": "test-secret-key-that-is-long-enough",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "POSTGRES_USER": "migration@example.com",
    "POSTGRES_PASSWORD": "p@ss:%/word#value",
    "POSTGRES_DB": "migration/test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "ENVIRONMENT": "test",
    "RUN_SEED_ON_STARTUP": "false",
    "ENABLE_SCHEDULER": "false",
  }


def _run_alembic(*arguments: str) -> str:
  result = subprocess.run(
    [sys.executable, "-m", "alembic", *arguments],
    check=True,
    capture_output=True,
    text=True,
    env=_alembic_environment(),
  )
  return result.stdout


def test_complete_alembic_upgrade_and_downgrade_sql_can_be_generated():
  upgrade_sql = _run_alembic("upgrade", "base:head", "--sql")
  downgrade_sql = _run_alembic("downgrade", "head:base", "--sql")

  assert "CREATE TABLE info_images" in upgrade_sql
  assert "DROP TABLE alembic_version" in downgrade_sql
  assert "fk_offices_address_id_addresses" in downgrade_sql
