from unittest.mock import AsyncMock

import pytest

from src.core import database
from src.core.exceptions import DomainValidationException


class SessionContext:
  def __init__(self, session):
    self.session = session

  async def __aenter__(self):
    return self.session

  async def __aexit__(self, exc_type, exc, traceback):
    return False


def make_session():
  session = AsyncMock()
  session.commit = AsyncMock()
  session.rollback = AsyncMock()
  session.info = {}
  return session


@pytest.mark.asyncio
async def test_successful_request_commits_once(monkeypatch):
  session = make_session()
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  assert await anext(dependency) is session

  with pytest.raises(StopAsyncIteration):
    await anext(dependency)

  session.commit.assert_awaited_once()
  session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_domain_error_rolls_back(monkeypatch):
  session = make_session()
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  await anext(dependency)
  error = DomainValidationException("Invalid state")

  with pytest.raises(DomainValidationException):
    await dependency.athrow(error)

  session.commit.assert_not_awaited()
  session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_error_rolls_back(monkeypatch):
  session = make_session()
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  await anext(dependency)

  with pytest.raises(RuntimeError):
    await dependency.athrow(RuntimeError("boom"))

  session.commit.assert_not_awaited()
  session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_error_triggers_rollback(monkeypatch):
  session = make_session()
  session.commit.side_effect = RuntimeError("commit failed")
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  await anext(dependency)

  with pytest.raises(RuntimeError, match="commit failed"):
    await anext(dependency)

  session.commit.assert_awaited_once()
  session.rollback.assert_awaited_once()


def test_http_database_dependencies_finish_before_response() -> None:
  """Every HTTP database dependency must use FastAPI's function scope."""

  from src.main import app

  for route in app.routes:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
      continue
    dependencies = list(dependant.dependencies)
    while dependencies:
      dependency = dependencies.pop()
      if dependency.call is database.get_db:
        assert dependency.scope == "function", route.path
      dependencies.extend(dependency.dependencies)


@pytest.mark.asyncio
async def test_commit_error_removes_registered_files(monkeypatch, tmp_path):
  from src.core.transaction_files import register_rollback_file

  session = make_session()
  session.commit.side_effect = RuntimeError("commit failed")
  staged_file = tmp_path / "staged.pdf"
  staged_file.write_bytes(b"content")
  register_rollback_file(session, staged_file)
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  await anext(dependency)

  with pytest.raises(RuntimeError, match="commit failed"):
    await anext(dependency)

  assert not staged_file.exists()


@pytest.mark.asyncio
async def test_successful_commit_removes_files_registered_for_deletion(
  monkeypatch,
  tmp_path,
):
  from src.core.transaction_files import register_commit_file_delete

  session = make_session()
  existing_file = tmp_path / "obsolete.jpg"
  existing_file.write_bytes(b"old")
  register_commit_file_delete(session, existing_file)
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  await anext(dependency)
  with pytest.raises(StopAsyncIteration):
    await anext(dependency)

  assert not existing_file.exists()


@pytest.mark.asyncio
async def test_rollback_keeps_files_registered_for_post_commit_deletion(
  monkeypatch,
  tmp_path,
):
  from src.core.transaction_files import register_commit_file_delete

  session = make_session()
  existing_file = tmp_path / "still-referenced.jpg"
  existing_file.write_bytes(b"old")
  register_commit_file_delete(session, existing_file)
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )

  dependency = database.get_db()
  await anext(dependency)
  with pytest.raises(RuntimeError, match="boom"):
    await dependency.athrow(RuntimeError("boom"))

  assert existing_file.exists()


@pytest.mark.asyncio
async def test_post_commit_cleanup_failure_does_not_rollback_committed_request(
  monkeypatch,
  caplog,
):
  session = make_session()
  monkeypatch.setattr(
    database,
    "AsyncSessionLocal",
    lambda: SessionContext(session),
  )
  monkeypatch.setattr(
    database,
    "cleanup_commit_file_deletes",
    lambda _session: (_ for _ in ()).throw(RuntimeError("cleanup bug")),
  )

  dependency = database.get_db()
  assert await anext(dependency) is session
  with pytest.raises(StopAsyncIteration):
    await anext(dependency)

  session.commit.assert_awaited_once()
  session.rollback.assert_not_awaited()
  assert "Unexpected post-commit file cleanup failure" in caplog.text
