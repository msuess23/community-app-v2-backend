from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
  """Load and validate application configuration from environment variables."""

  # App configuration
  PROJECT_NAME: str
  BASE_URL: str
  ENVIRONMENT: Literal["development", "test", "production"] = "development"
  CORS_ORIGINS: list[str] = Field(
    default_factory=lambda: [
      "http://localhost:3000",
      "http://localhost:5173",
    ]
  )

  # Security and JWT configuration
  SECRET_KEY: str = Field(min_length=32)
  ALGORITHM: Literal["HS256"] = "HS256"
  ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(gt=0)
  REFRESH_TOKEN_EXPIRE_DAYS: int = Field(gt=0)

  # Optional startup tasks
  RUN_SEED_ON_STARTUP: bool = False
  SEED_DEFAULT_PASSWORD: str | None = None
  ENABLE_SCHEDULER: bool = True
  DEEP_ANONYMIZATION_HOUR: int = Field(default=3, ge=0, le=23)
  DEEP_ANONYMIZATION_MINUTE: int = Field(default=0, ge=0, le=59)
  CITIZEN_HISTORY_RETENTION_DAYS: int = Field(default=180, ge=1)

  # Ticket image storage used by the event-sourced media projection
  TICKET_MEDIA_ROOT: str = "./data/ticket-media"
  TICKET_IMAGE_MAX_BYTES: int = Field(default=5 * 1024 * 1024, ge=1)
  TICKET_IMAGE_ALLOWED_MIME_TYPES: list[str] = Field(
    default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
  )

  # Ordinary CRUD image storage for public information notices
  INFO_MEDIA_ROOT: str = "./data/info-media"
  INFO_IMAGE_MAX_BYTES: int = Field(default=5 * 1024 * 1024, ge=1)
  INFO_IMAGE_ALLOWED_MIME_TYPES: list[str] = Field(
    default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
  )

  # Versioned appointment PDF storage
  APPOINTMENT_DOCUMENT_ROOT: str = "./data/appointment-documents"
  APPOINTMENT_DOCUMENT_MAX_BYTES: int = Field(default=10 * 1024 * 1024, ge=1)

  # Database atomic variables
  POSTGRES_USER: str = Field(min_length=1)
  POSTGRES_PASSWORD: str = Field(min_length=1)
  POSTGRES_DB: str = Field(min_length=1)
  POSTGRES_HOST: str = Field(min_length=1)
  POSTGRES_PORT: int = Field(gt=0, le=65535)

  @computed_field
  @property
  def DATABASE_URL(self) -> str:
    """Construct an escaped async SQLAlchemy URL from atomic settings."""

    return URL.create(
      drivername="postgresql+asyncpg",
      username=self.POSTGRES_USER,
      password=self.POSTGRES_PASSWORD,
      host=self.POSTGRES_HOST,
      port=self.POSTGRES_PORT,
      database=self.POSTGRES_DB,
    ).render_as_string(hide_password=False)

  @model_validator(mode="after")
  def validate_startup_configuration(self) -> "Settings":
    """Reject unsafe or incomplete startup configuration combinations."""

    if self.ENVIRONMENT == "production" and self.RUN_SEED_ON_STARTUP:
      raise ValueError("RUN_SEED_ON_STARTUP must be disabled in production")

    if self.RUN_SEED_ON_STARTUP and not self.SEED_DEFAULT_PASSWORD:
      raise ValueError(
        "SEED_DEFAULT_PASSWORD is required when RUN_SEED_ON_STARTUP is enabled"
      )

    if self.SEED_DEFAULT_PASSWORD is not None and len(self.SEED_DEFAULT_PASSWORD) < 8:
      raise ValueError("SEED_DEFAULT_PASSWORD must contain at least 8 characters")

    if not self.TICKET_IMAGE_ALLOWED_MIME_TYPES:
      raise ValueError("TICKET_IMAGE_ALLOWED_MIME_TYPES must not be empty")
    if not self.INFO_IMAGE_ALLOWED_MIME_TYPES:
      raise ValueError("INFO_IMAGE_ALLOWED_MIME_TYPES must not be empty")

    return self

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=True,
    extra="ignore",
  )


settings = Settings()
