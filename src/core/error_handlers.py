from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.exceptions import DomainException
from src.core.request_id import REQUEST_ID_HEADER


logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
  return getattr(request.state, "request_id", "unknown")


def _error_response(
  request: Request,
  *,
  status_code: int,
  code: str,
  message: str,
  details: Any = None,
  headers: dict[str, str] | None = None,
) -> JSONResponse:
  request_id = _request_id(request)
  response_headers = dict(headers) if headers else {}
  response_headers[REQUEST_ID_HEADER] = request_id

  return JSONResponse(
    status_code=status_code,
    content={
      "error": {
        "code": code,
        "message": message,
        "details": details if details is not None else [],
        "request_id": request_id,
      }
    },
    headers=response_headers,
  )


async def domain_exception_handler(
  request: Request,
  exc: DomainException,
) -> JSONResponse:
  return _error_response(
    request,
    status_code=exc.status_code,
    code=exc.error_code,
    message=exc.message,
    details=exc.details,
    headers=exc.headers,
  )


async def request_validation_exception_handler(
  request: Request,
  exc: RequestValidationError,
) -> JSONResponse:
  details = []
  for error in exc.errors():
    location = [str(part) for part in error.get("loc", ())]
    details.append(
      {
        "field": ".".join(location),
        "message": error.get("msg", "Invalid value"),
        "type": error.get("type", "validation_error"),
      }
    )

  return _error_response(
    request,
    status_code=422,
    code="REQUEST_VALIDATION_FAILED",
    message="The request contains invalid data.",
    details=details,
  )


async def http_exception_handler(
  request: Request,
  exc: StarletteHTTPException,
) -> JSONResponse:
  try:
    reason = HTTPStatus(exc.status_code).phrase.upper().replace(" ", "_")
  except ValueError:
    reason = "HTTP_ERROR"

  message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
  return _error_response(
    request,
    status_code=exc.status_code,
    code=f"HTTP_{exc.status_code}_{reason}",
    message=message,
    headers=dict(exc.headers) if exc.headers else None,
  )


def _sqlstate(exc: IntegrityError) -> str | None:
  candidates = [
    exc.orig,
    getattr(exc.orig, "__cause__", None),
    getattr(exc.orig, "__context__", None),
  ]
  for candidate in candidates:
    if candidate is None:
      continue
    value = getattr(candidate, "sqlstate", None) or getattr(
      candidate,
      "pgcode",
      None,
    )
    if value:
      return str(value)
  return None


async def integrity_error_handler(
  request: Request,
  exc: IntegrityError,
) -> JSONResponse:
  sqlstate = _sqlstate(exc)
  logger.warning(
    "Database integrity constraint rejected a request",
    extra={"request_id": _request_id(request), "sqlstate": sqlstate},
  )

  if sqlstate == "23505":
    status_code = status.HTTP_409_CONFLICT
    code = "UNIQUE_CONSTRAINT_VIOLATION"
    message = "A resource with the submitted unique values already exists."
  elif sqlstate == "23503":
    status_code = status.HTTP_409_CONFLICT
    code = "FOREIGN_KEY_CONSTRAINT_VIOLATION"
    message = "The request references a resource that does not exist or is still in use."
  elif sqlstate in {"23502", "23514"}:
    status_code = 422
    code = "DATA_CONSTRAINT_VIOLATION"
    message = "The submitted data violates a database constraint."
  else:
    status_code = status.HTTP_409_CONFLICT
    code = "DATA_INTEGRITY_CONFLICT"
    message = "The request conflicts with persisted data."

  return _error_response(
    request,
    status_code=status_code,
    code=code,
    message=message,
  )


async def response_validation_exception_handler(
  request: Request,
  exc: ResponseValidationError,
) -> JSONResponse:
  logger.error(
    "Response validation failed",
    extra={"request_id": _request_id(request), "errors": exc.errors()},
  )
  return _error_response(
    request,
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    code="RESPONSE_VALIDATION_FAILED",
    message="The server could not serialize its response.",
  )


async def sqlalchemy_exception_handler(
  request: Request,
  exc: SQLAlchemyError,
) -> JSONResponse:
  logger.error(
    "Unexpected database error",
    extra={"request_id": _request_id(request)},
    exc_info=exc,
  )
  return _error_response(
    request,
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    code="DATABASE_ERROR",
    message="A database operation failed.",
  )


async def unhandled_exception_handler(
  request: Request,
  exc: Exception,
) -> JSONResponse:
  logger.error(
    "Unhandled application error",
    extra={"request_id": _request_id(request)},
    exc_info=exc,
  )
  return _error_response(
    request,
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    code="INTERNAL_SERVER_ERROR",
    message="An unexpected server error occurred.",
  )


def register_exception_handlers(app: FastAPI) -> None:
  """Register one stable JSON error contract for all relevant error classes."""
  app.add_exception_handler(DomainException, domain_exception_handler)
  app.add_exception_handler(
    RequestValidationError,
    request_validation_exception_handler,
  )
  app.add_exception_handler(
    ResponseValidationError,
    response_validation_exception_handler,
  )
  app.add_exception_handler(StarletteHTTPException, http_exception_handler)
  app.add_exception_handler(IntegrityError, integrity_error_handler)
  app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
  app.add_exception_handler(Exception, unhandled_exception_handler)
