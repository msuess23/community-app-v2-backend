import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import DomainException

logger = logging.getLogger(__name__)


def _error_response(
  *,
  status_code: int,
  error_code: str,
  message: str,
  details: list[dict[str, Any]] | None = None,
  headers: dict[str, str] | None = None,
) -> JSONResponse:
  return JSONResponse(
    status_code=status_code,
    content={
      "error_code": error_code,
      "message": message,
      "details": details or [],
    },
    headers=headers,
  )


async def domain_exception_handler(
  request: Request,
  exc: DomainException,
) -> JSONResponse:
  del request
  headers = None
  if exc.status_code == status.HTTP_401_UNAUTHORIZED:
    headers = {"WWW-Authenticate": "Bearer"}

  return _error_response(
    status_code=exc.status_code,
    error_code=exc.error_code,
    message=exc.message,
    details=exc.details,
    headers=headers,
  )


async def request_validation_exception_handler(
  request: Request,
  exc: RequestValidationError,
) -> JSONResponse:
  del request
  details: list[dict[str, Any]] = []

  for error in exc.errors():
    location = [str(part) for part in error.get("loc", ())]
    if location and location[0] in {"body", "query", "path", "header", "cookie"}:
      location = location[1:]

    details.append(
      {
        "field": ".".join(location) or "request",
        "message": error.get("msg", "Invalid value"),
      }
    )

  return _error_response(
    status_code=422,
    error_code="VALIDATION_ERROR",
    message="The request contains invalid data.",
    details=details,
  )


async def http_exception_handler(
  request: Request,
  exc: StarletteHTTPException,
) -> JSONResponse:
  del request
  message = str(exc.detail)
  error_code = "HTTP_ERROR"
  if exc.status_code == status.HTTP_401_UNAUTHORIZED:
    error_code = "UNAUTHORIZED"
  elif exc.status_code == status.HTTP_403_FORBIDDEN:
    error_code = "FORBIDDEN"
  elif exc.status_code == status.HTTP_404_NOT_FOUND:
    error_code = "RESOURCE_NOT_FOUND"

  return _error_response(
    status_code=exc.status_code,
    error_code=error_code,
    message=message,
    headers=exc.headers,
  )


def _integrity_error_metadata(exc: IntegrityError) -> tuple[int, str, str]:
  original = exc.orig
  sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
  constraint_name = getattr(getattr(original, "diag", None), "constraint_name", None)

  if constraint_name and "email" in constraint_name.lower():
    return (
      status.HTTP_409_CONFLICT,
      "EMAIL_ALREADY_REGISTERED",
      "Email already registered",
    )

  if sqlstate == "23505":
    return (
      status.HTTP_409_CONFLICT,
      "RESOURCE_CONFLICT",
      "A resource with these unique values already exists.",
    )

  if sqlstate == "23503":
    return (
      status.HTTP_409_CONFLICT,
      "REFERENCE_CONFLICT",
      "The requested operation conflicts with a referenced resource.",
    )

  if sqlstate in {"23502", "23514"}:
    return (
      422,
      "DATABASE_CONSTRAINT_ERROR",
      "The data violates a database constraint.",
    )

  return (
    status.HTTP_500_INTERNAL_SERVER_ERROR,
    "DATABASE_ERROR",
    "A database error occurred.",
  )


async def integrity_error_handler(
  request: Request,
  exc: IntegrityError,
) -> JSONResponse:
  del request
  status_code, error_code, message = _integrity_error_metadata(exc)

  if status_code >= 500:
    logger.error(
      "Unhandled database integrity error",
      exc_info=(type(exc), exc, exc.__traceback__),
    )

  return _error_response(
    status_code=status_code,
    error_code=error_code,
    message=message,
  )


async def unexpected_exception_handler(
  request: Request,
  exc: Exception,
) -> JSONResponse:
  logger.error(
    "Unhandled exception while processing %s %s",
    request.method,
    request.url.path,
    exc_info=(type(exc), exc, exc.__traceback__),
  )
  return _error_response(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    error_code="INTERNAL_SERVER_ERROR",
    message="An unexpected error occurred.",
  )
