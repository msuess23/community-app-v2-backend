from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.core.config import settings
from src.core.transaction_files import (
  clear_commit_file_deletes,
  clear_rollback_files,
  cleanup_commit_file_deletes,
  cleanup_rollback_files,
)

# Create async engine for PostgreSQL
engine = create_async_engine(
  settings.DATABASE_URL,
  echo=False,
  pool_size=10,
  max_overflow=20,
  pool_timeout=30,
  pool_recycle=1800,
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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
  """Provide one transaction-scoped session and commit it before the response."""

  async with AsyncSessionLocal() as session:
    try:
      yield session
      await session.commit()
      cleanup_commit_file_deletes(session)
      clear_rollback_files(session)
    except Exception:
      await session.rollback()
      clear_commit_file_deletes(session)
      cleanup_rollback_files(session)
      raise
