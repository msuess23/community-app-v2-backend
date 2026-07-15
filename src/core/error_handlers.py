import logging
from typing import Any

from fastapi import FastAPI, Request, status
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
  details: Any = None,
  headers: dict[str, str] | None = None,
) -> JSONResponse:
  return JSONResponse(
    status_code=status_code,
    content={
      "error_code": error_code,
      "message": message,
      "details": details if details is not None else [],
    },
    headers=headers,
  )


async def domain_exception_handler(
  _request: Request,
  exc: DomainException,
) -> JSONResponse:
  return _error_response(
    status_code=exc.status_code,
    error_code=exc.error_code,
    message=exc.message,
    details=exc.details,
    headers=exc.headers,
  )


async def request_validation_exception_handler(
  _request: Request,
  exc: RequestValidationError,
) -> JSONResponse:
  details = [
    {
      "field": ".".join(str(part) for part in error.get("loc", ())),
      "message": error.get("msg", "Invalid value"),
      "type": error.get("type", "validation_error"),
    }
    for error in exc.errors()
  ]
  return _error_response(
    status_code=422,
    error_code="REQUEST_VALIDATION_FAILED",
    message="The request contains invalid data.",
    details=details,
  )


async def http_exception_handler(
  _request: Request,
  exc: StarletteHTTPException,
) -> JSONResponse:
  message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
  return _error_response(
    status_code=exc.status_code,
    error_code=f"HTTP_{exc.status_code}",
    message=message,
    headers=dict(exc.headers) if exc.headers else None,
  )


def _sqlstate(exc: IntegrityError) -> str | None:
  current: BaseException | None = exc.orig
  for _ in range(3):
    if current is None:
      return None
    value = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
    if value:
      return str(value)
    current = getattr(current, "__cause__", None)
  return None


async def integrity_error_handler(
  _request: Request,
  exc: IntegrityError,
) -> JSONResponse:
  sqlstate = _sqlstate(exc)
  logger.warning("Database constraint rejected a request", extra={"sqlstate": sqlstate})

  if sqlstate == "23505":
    return _error_response(
      status_code=status.HTTP_409_CONFLICT,
      error_code="UNIQUE_CONSTRAINT_VIOLATION",
      message="A resource with these unique values already exists.",
    )
  if sqlstate == "23503":
    return _error_response(
      status_code=status.HTTP_409_CONFLICT,
      error_code="FOREIGN_KEY_CONSTRAINT_VIOLATION",
      message="A referenced resource does not exist or is still in use.",
    )
  return _error_response(
    status_code=422,
    error_code="DATA_CONSTRAINT_VIOLATION",
    message="The submitted data violates a database constraint.",
  )


async def unhandled_exception_handler(
  _request: Request,
  exc: Exception,
) -> JSONResponse:
  logger.error(
    "Unhandled application error",
    exc_info=(type(exc), exc, exc.__traceback__),
  )
  return _error_response(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    error_code="INTERNAL_SERVER_ERROR",
    message="An unexpected server error occurred.",
  )


def register_exception_handlers(app: FastAPI) -> None:
  app.add_exception_handler(DomainException, domain_exception_handler)
  app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
  app.add_exception_handler(StarletteHTTPException, http_exception_handler)
  app.add_exception_handler(IntegrityError, integrity_error_handler)
  app.add_exception_handler(Exception, unhandled_exception_handler)
