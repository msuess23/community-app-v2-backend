from typing import Any

from fastapi import status


ErrorDetails = list[dict[str, Any]]


class DomainException(Exception):
  """Base class for expected application errors."""

  def __init__(
    self,
    message: str,
    *,
    error_code: str = "DOMAIN_ERROR",
    status_code: int = status.HTTP_400_BAD_REQUEST,
    details: ErrorDetails | None = None,
  ) -> None:
    self.message = message
    self.error_code = error_code
    self.status_code = status_code
    self.details = details or []
    super().__init__(message)


class ResourceNotFoundException(DomainException):
  def __init__(
    self,
    message: str = "The requested resource was not found.",
    *,
    error_code: str = "RESOURCE_NOT_FOUND",
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_404_NOT_FOUND,
    )


class ConflictException(DomainException):
  def __init__(
    self,
    message: str = "The request conflicts with the current resource state.",
    *,
    error_code: str = "RESOURCE_CONFLICT",
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_409_CONFLICT,
    )


class DomainValidationException(DomainException):
  def __init__(
    self,
    message: str = "The request contains invalid data.",
    *,
    error_code: str = "DOMAIN_VALIDATION_ERROR",
    details: ErrorDetails | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=422,
      details=details,
    )


class UnauthorizedException(DomainException):
  """Authentication failed because credentials are missing or invalid."""

  def __init__(self, message: str = "Could not validate credentials") -> None:
    super().__init__(
      message,
      error_code="UNAUTHORIZED",
      status_code=status.HTTP_401_UNAUTHORIZED,
    )


class ForbiddenException(DomainException):
  """The authenticated user is not allowed to access the resource."""

  def __init__(self, message: str = "Insufficient permissions") -> None:
    super().__init__(
      message,
      error_code="FORBIDDEN",
      status_code=status.HTTP_403_FORBIDDEN,
    )


class WorkflowValidationException(DomainValidationException):
  def __init__(self, message: str = "Invalid workflow operation.") -> None:
    super().__init__(
      message,
      error_code="WORKFLOW_VALIDATION_FAILED",
    )
