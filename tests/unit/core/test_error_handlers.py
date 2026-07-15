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


def make_request() -> Request:
  return Request({"type": "http", "method": "GET", "path": "/test", "headers": []})


def response_json(response) -> dict:
  return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_domain_error_uses_simple_error_contract():
  response = await domain_exception_handler(
    make_request(),
    ResourceNotFoundException("User not found", error_code="USER_NOT_FOUND"),
  )

  assert response.status_code == status.HTTP_404_NOT_FOUND
  assert response_json(response) == {
    "error_code": "USER_NOT_FOUND",
    "message": "User not found",
    "details": [],
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
  assert payload["error_code"] == "REQUEST_VALIDATION_FAILED"
  assert payload["details"] == [
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
  assert payload["error_code"] == "UNIQUE_CONSTRAINT_VIOLATION"
  assert "INSERT INTO" not in response.body.decode("utf-8")
