from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  PROJECT_NAME: str
  BASE_URL: str
  ENVIRONMENT: Literal["development", "test", "production"] = "development"
  CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
  ]

  SECRET_KEY: str = Field(min_length=32)
  ALGORITHM: Literal["HS256"] = "HS256"
  JWT_ISSUER: str = "community-app-backend"
  JWT_AUDIENCE: str = "community-app-clients"
  JWT_LEEWAY_SECONDS: int = 5
  ACCESS_TOKEN_EXPIRE_MINUTES: int
  REFRESH_TOKEN_EXPIRE_DAYS: int
  PASSWORD_RESET_EXPIRE_MINUTES: int = Field(default=15, ge=5, le=60)

  POSTGRES_USER: str
  POSTGRES_PASSWORD: str
  POSTGRES_DB: str
  POSTGRES_HOST: str
  POSTGRES_PORT: int

  SEED_DEFAULT_PASSWORD: str | None = Field(default=None, min_length=8, max_length=128)

  @computed_field
  @property
  def DATABASE_URL(self) -> str:
    return (
      f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
      f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    )

  model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    case_sensitive=True,
    extra="ignore",
  )


settings = Settings()
