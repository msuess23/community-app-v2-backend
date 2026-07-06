from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.core.config import settings

# Create async engine for PostgreSQL
engine = create_async_engine(
  settings.DATABASE_URL,
  echo=False,
  future=True
)

# Configure session factory
AsyncSessionLocal = async_sessionmaker(
  bind=engine,
  class_=AsyncSession,
  expire_on_commit=False,
  autocommit=False,
  autoflush=False,
)

# Base class for ORM models
Base = declarative_base()

# FastAPI dependency for DB sessions
async def get_db() -> AsyncGenerator[AsyncSession, None]:
  async with AsyncSessionLocal() as session:
    try:
      yield session
    except Exception:
      await session.rollback()
      raise
    finally:
      await session.close()