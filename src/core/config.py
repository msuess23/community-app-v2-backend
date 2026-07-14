from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

from pydantic import Field, computed_field

class Settings(BaseSettings):
  # App configuration
  PROJECT_NAME: str
  BASE_URL: str
    
  # Security and JWT configuration
  SECRET_KEY: str = Field(min_length=32)
  ALGORITHM: Literal["HS256"] = "HS256"
  JWT_ISSUER: str = "community-app-backend"
  JWT_AUDIENCE: str = "community-app-clients"
  JWT_LEEWAY_SECONDS: int = 5
  ACCESS_TOKEN_EXPIRE_MINUTES: int
  REFRESH_TOKEN_EXPIRE_DAYS: int

  # Password-reset configuration
  PASSWORD_RESET_EXPIRE_MINUTES: int = Field(default=15, ge=5, le=60)
  PASSWORD_RESET_MAX_ATTEMPTS: int = Field(default=5, ge=1, le=10)
  PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS: int = Field(
    default=60,
    ge=0,
    le=3600,
  )

  # Database atomic variables
  POSTGRES_USER: str
  POSTGRES_PASSWORD: str
  POSTGRES_DB: str
  POSTGRES_HOST: str
  POSTGRES_PORT: int

  # Email Configuration (New)
  SMTP_HOST: str = ""
  SMTP_PORT: int = 587
  SMTP_USER: str = ""
  SMTP_PASSWORD: str = ""
  SMTP_TLS: bool = True
  SMTP_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)

  # Construct the DATABASE_URL dynamically from atomic variables
  @computed_field
  @property
  def DATABASE_URL(self) -> str:
    return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

  # Pydantic configuration to strictly load from .env file
  model_config = SettingsConfigDict(
    env_file=".env", 
    env_file_encoding="utf-8", 
    case_sensitive=True,
    extra="ignore"
  )

# Instantiate settings to be imported across the application
settings = Settings()