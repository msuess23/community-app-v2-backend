from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field

class Settings(BaseSettings):
  # App configuration
  PROJECT_NAME: str
  BASE_URL: str
    
  # Security and JWT configuration
  SECRET_KEY: str
  ALGORITHM: str
  ACCESS_TOKEN_EXPIRE_MINUTES: int
  REFRESH_TOKEN_EXPIRE_DAYS: int

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