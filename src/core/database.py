from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
  AsyncSession,
  async_sessionmaker,
  create_async_engine,
)
from sqlalchemy.orm import declarative_base

from src.core.config import settings


engine = create_async_engine(
  settings.DATABASE_URL,
  echo=False,
  pool_size=10,
  max_overflow=20,
  pool_timeout=30,
  pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
  bind=engine,
  class_=AsyncSession,
  expire_on_commit=False,
  autoflush=False,
)

NAMING_CONVENTION = {
  "ix": "ix_%(table_name)s_%(column_0_name)s",
  "uq": "uq_%(table_name)s_%(column_0_name)s",
  "ck": "ck_%(table_name)s_%(column_0_name)s",
  "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
  "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


@asynccontextmanager
async def transactional_session() -> AsyncIterator[AsyncSession]:
  """
  Provide exactly one transaction boundary for a complete application use case.

  Repositories and services stage work only. A successful caller is committed
  once; every ordinary exception rolls the complete transaction back.
  """
  async with AsyncSessionLocal() as session:
    try:
      yield session
    except BaseException:
      await session.rollback()
      raise
    else:
      try:
        await session.commit()
      except BaseException:
        await session.rollback()
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
  """FastAPI dependency exposing the request-scoped transactional session."""
  async with transactional_session() as session:
    yield session
