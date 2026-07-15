from typing import Any, Dict, Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse


class DomainException(Exception):
  """Base class for application errors with a stable API representation."""

  def __init__(
    self,
    message: str,
    error_code: str = "INTERNAL_SERVER_ERROR",
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    details: Optional[Dict[str, Any]] = None,
  ):
    self.message = message
    self.error_code = error_code
    self.status_code = status_code
    self.details = details
    super().__init__(self.message)


class ResourceNotFoundException(DomainException):
  def __init__(self, message: str = "The requested resource was not found."):
    super().__init__(
      message=message,
      error_code="RESOURCE_NOT_FOUND",
      status_code=status.HTTP_404_NOT_FOUND,
    )


class UnauthorizedException(DomainException):
  """Authentication failed because credentials are missing or invalid."""

  def __init__(self, message: str = "Could not validate credentials"):
    super().__init__(
      message=message,
      error_code="UNAUTHORIZED",
      status_code=status.HTTP_401_UNAUTHORIZED,
    )


class ForbiddenException(DomainException):
  """The authenticated user is not allowed to access the resource."""

  def __init__(self, message: str = "Insufficient permissions"):
    super().__init__(
      message=message,
      error_code="FORBIDDEN",
      status_code=status.HTTP_403_FORBIDDEN,
    )


class WorkflowValidationException(DomainException):
  def __init__(self, message: str = "Invalid workflow operation."):
    super().__init__(
      message=message,
      error_code="WORKFLOW_VALIDATION_FAILED",
      status_code=status.HTTP_400_BAD_REQUEST,
    )


async def domain_exception_handler(
  request: Request,
  exc: DomainException,
) -> JSONResponse:
  content: Dict[str, Any] = {
    "error_code": exc.error_code,
    "message": exc.message,
  }
  if exc.details:
    content["details"] = exc.details

  headers = None
  if exc.status_code == status.HTTP_401_UNAUTHORIZED:
    headers = {"WWW-Authenticate": "Bearer"}

  return JSONResponse(
    status_code=exc.status_code,
    content=content,
    headers=headers,
  )
