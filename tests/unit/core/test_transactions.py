from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.core import database


@dataclass
class FakeSession:
  commits: int = 0
  rollbacks: int = 0
  closed: bool = False
  fail_commit: bool = False

  async def __aenter__(self):
    return self

  async def __aexit__(self, exc_type, exc, tb):
    self.closed = True

  async def commit(self) -> None:
    self.commits += 1
    if self.fail_commit:
      raise RuntimeError("commit failed")

  async def rollback(self) -> None:
    self.rollbacks += 1


@pytest.mark.asyncio
async def test_transactional_session_commits_once_on_success(monkeypatch):
  session = FakeSession()
  monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

  async with database.transactional_session() as yielded:
    assert yielded is session

  assert session.commits == 1
  assert session.rollbacks == 0
  assert session.closed is True


@pytest.mark.asyncio
async def test_transactional_session_rolls_back_on_error(monkeypatch):
  session = FakeSession()
  monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

  with pytest.raises(RuntimeError, match="boom"):
    async with database.transactional_session():
      raise RuntimeError("boom")

  assert session.commits == 0
  assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_failed_commit_is_rolled_back(monkeypatch):
  session = FakeSession(fail_commit=True)
  monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

  with pytest.raises(RuntimeError, match="commit failed"):
    async with database.transactional_session():
      pass

  assert session.commits == 1
  assert session.rollbacks == 1


def test_response_validation_failure_rolls_back_before_commit(monkeypatch):
  from fastapi import Depends, FastAPI
  from fastapi.testclient import TestClient
  from pydantic import BaseModel

  from src.core.error_handlers import register_exception_handlers

  session = FakeSession()
  monkeypatch.setattr(database, "AsyncSessionLocal", lambda: session)

  class ResponseModel(BaseModel):
    value: int

  test_app = FastAPI()
  register_exception_handlers(test_app)

  @test_app.get("/invalid", response_model=ResponseModel)
  async def invalid_response(db=Depends(database.get_db)):
    return {"value": "not-an-integer"}

  with TestClient(test_app, raise_server_exceptions=False) as client:
    response = client.get("/invalid")

  assert response.status_code == 500
  assert response.json()["error_code"] == "INTERNAL_SERVER_ERROR"
  assert session.commits == 0
  assert session.rollbacks == 1
