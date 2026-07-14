from __future__ import annotations

import json

import pytest
from fastapi import status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from src.core.error_handlers import (
  domain_exception_handler,
  integrity_error_handler,
  request_validation_exception_handler,
)
from src.core.exceptions import ResourceNotFoundException


REQUEST_ID = "a8df1b90-2c2e-42e7-b2cb-6ec4a9cbcc13"


def make_request() -> Request:
  return Request(
    {
      "type": "http",
      "method": "GET",
      "path": "/test",
      "headers": [],
      "state": {"request_id": REQUEST_ID},
    }
  )


def response_json(response) -> dict:
  return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_domain_error_uses_uniform_envelope():
  response = await domain_exception_handler(
    make_request(),
    ResourceNotFoundException(
      "User not found",
      error_code="USER_NOT_FOUND",
    ),
  )

  assert response.status_code == status.HTTP_404_NOT_FOUND
  assert response.headers["X-Request-ID"] == REQUEST_ID
  assert response_json(response) == {
    "error": {
      "code": "USER_NOT_FOUND",
      "message": "User not found",
      "details": [],
      "request_id": REQUEST_ID,
    }
  }


@pytest.mark.asyncio
async def test_request_validation_does_not_echo_sensitive_input():
  response = await request_validation_exception_handler(
    make_request(),
    RequestValidationError(
      [
        {
          "type": "string_too_short",
          "loc": ("body", "password"),
          "msg": "String should have at least 8 characters",
          "input": "top-secret-password",
        }
      ]
    ),
  )
  payload = response_json(response)

  assert response.status_code == 422
  assert payload["error"]["code"] == "REQUEST_VALIDATION_FAILED"
  assert payload["error"]["details"] == [
    {
      "field": "body.password",
      "message": "String should have at least 8 characters",
      "type": "string_too_short",
    }
  ]
  assert "top-secret-password" not in response.body.decode("utf-8")


class UniqueViolation(Exception):
  sqlstate = "23505"


@pytest.mark.asyncio
async def test_unique_integrity_error_is_translated_to_conflict():
  response = await integrity_error_handler(
    make_request(),
    IntegrityError("INSERT INTO users ...", {}, UniqueViolation()),
  )
  payload = response_json(response)

  assert response.status_code == status.HTTP_409_CONFLICT
  assert payload["error"]["code"] == "UNIQUE_CONSTRAINT_VIOLATION"
  assert "INSERT INTO" not in response.body.decode("utf-8")
