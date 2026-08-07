import json

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from src.core.error_handlers import (
  domain_exception_handler,
  integrity_error_handler,
  request_validation_exception_handler,
)
from src.core.exceptions import ResourceNotFoundException


def make_request() -> Request:
  return Request({"type": "http", "method": "POST", "path": "/test", "headers": []})


def response_json(response):
  return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_domain_error_uses_uniform_response_format():
  response = await domain_exception_handler(
    make_request(),
    ResourceNotFoundException("User not found", error_code="USER_NOT_FOUND"),
  )

  assert response.status_code == 404
  assert response_json(response) == {
    "error_code": "USER_NOT_FOUND",
    "message": "User not found",
    "details": [],
  }


@pytest.mark.asyncio
async def test_validation_error_does_not_echo_sensitive_input():
  exception = RequestValidationError(
    [
      {
        "type": "string_too_short",
        "loc": ("body", "password"),
        "msg": "String should have at least 8 characters",
        "input": "super-secret-password",
      }
    ]
  )

  response = await request_validation_exception_handler(make_request(), exception)
  body = response_json(response)

  assert response.status_code == 422
  assert body["error_code"] == "VALIDATION_ERROR"
  assert body["details"] == [
    {
      "field": "password",
      "message": "String should have at least 8 characters",
    }
  ]
  assert "super-secret-password" not in response.body.decode("utf-8")


class UniqueViolation:
  sqlstate = "23505"

  class diag:
    constraint_name = "users_email_key"


@pytest.mark.asyncio
async def test_duplicate_email_integrity_error_returns_conflict():
  exception = IntegrityError("insert", {}, UniqueViolation())

  response = await integrity_error_handler(make_request(), exception)

  assert response.status_code == 409
  assert response_json(response)["error_code"] == "EMAIL_ALREADY_REGISTERED"
