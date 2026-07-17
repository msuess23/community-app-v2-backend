from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

  # Database atomic variables
  POSTGRES_USER: str = Field(min_length=1)
  POSTGRES_PASSWORD: str = Field(min_length=1)
  POSTGRES_DB: str = Field(min_length=1)
  POSTGRES_HOST: str = Field(min_length=1)
  POSTGRES_PORT: int = Field(gt=0, le=65535)

  @computed_field
  @property
  def DATABASE_URL(self) -> str:
    """Constructs the async SQLAlchemy URL from the atomic settings."""
    return (
      f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
      f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    )

  @model_validator(mode="after")
  def validate_startup_configuration(self) -> "Settings":
    if self.ENVIRONMENT == "production" and self.RUN_SEED_ON_STARTUP:
      raise ValueError("RUN_SEED_ON_STARTUP must be disabled in production")

    if self.RUN_SEED_ON_STARTUP and not self.SEED_DEFAULT_PASSWORD:
      raise ValueError(
        "SEED_DEFAULT_PASSWORD is required when RUN_SEED_ON_STARTUP is enabled"
      )

    if self.SEED_DEFAULT_PASSWORD is not None and len(self.SEED_DEFAULT_PASSWORD) < 8:
      raise ValueError("SEED_DEFAULT_PASSWORD must contain at least 8 characters")

    return self

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=True,
    extra="ignore",
  )


settings = Settings()
