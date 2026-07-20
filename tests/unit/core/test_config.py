import pytest
from pydantic import ValidationError

from src.core.config import Settings


BASE_SETTINGS = {
  "PROJECT_NAME": "Test Backend",
  "BASE_URL": "/api/v1",
  "SECRET_KEY": "test-secret-key-that-is-at-least-32-characters",
  "ACCESS_TOKEN_EXPIRE_MINUTES": 15,
  "REFRESH_TOKEN_EXPIRE_DAYS": 7,
  "POSTGRES_USER": "test",
  "POSTGRES_PASSWORD": "test",
  "POSTGRES_DB": "test",
  "POSTGRES_HOST": "localhost",
  "POSTGRES_PORT": 5432,
}


def create_settings(**overrides) -> Settings:
  return Settings(_env_file=None, **{**BASE_SETTINGS, **overrides})


def test_production_disallows_automatic_demo_seeding():
  with pytest.raises(ValidationError, match="disabled in production"):
    create_settings(
      ENVIRONMENT="production",
      RUN_SEED_ON_STARTUP=True,
      SEED_DEFAULT_PASSWORD="password123",
    )


def test_startup_seeding_requires_a_demo_password():
  with pytest.raises(ValidationError, match="SEED_DEFAULT_PASSWORD"):
    create_settings(RUN_SEED_ON_STARTUP=True)


def test_scheduler_and_cors_settings_are_configurable():
  configured = create_settings(
    ENABLE_SCHEDULER=False,
    DEEP_ANONYMIZATION_HOUR=4,
    DEEP_ANONYMIZATION_MINUTE=30,
    CITIZEN_HISTORY_RETENTION_DAYS=90,
    CORS_ORIGINS=["http://localhost:5173"],
  )

  assert configured.ENABLE_SCHEDULER is False
  assert configured.DEEP_ANONYMIZATION_HOUR == 4
  assert configured.DEEP_ANONYMIZATION_MINUTE == 30
  assert configured.CITIZEN_HISTORY_RETENTION_DAYS == 90
  assert configured.CORS_ORIGINS == ["http://localhost:5173"]


def test_database_url_escapes_credentials_with_reserved_characters():
  from sqlalchemy.engine import make_url

  password = "p@ss:%/word#value"
  configured = create_settings(
    POSTGRES_USER="user@example.com",
    POSTGRES_PASSWORD=password,
    POSTGRES_DB="community/test",
  )

  parsed = make_url(configured.DATABASE_URL)

  assert parsed.username == "user@example.com"
  assert parsed.password == password
  assert parsed.database == "community/test"
  assert "%40" in configured.DATABASE_URL
  assert "%2F" in configured.DATABASE_URL
