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
    """Initialize a domain exception with HTTP and machine-readable metadata."""

    self.message = message
    self.error_code = error_code
    self.status_code = status_code
    self.details = details or []
    super().__init__(message)


class ResourceNotFoundException(DomainException):
  """Represent a missing domain resource as an HTTP 404 error."""

  def __init__(
    self,
    message: str = "The requested resource was not found.",
    *,
    error_code: str = "RESOURCE_NOT_FOUND",
  ) -> None:
    """Initialize a not-found exception with a stable error code."""

    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_404_NOT_FOUND,
    )


class ConflictException(DomainException):
  """Represent a domain state conflict as an HTTP 409 error."""

  def __init__(
    self,
    message: str = "The request conflicts with the current resource state.",
    *,
    error_code: str = "RESOURCE_CONFLICT",
  ) -> None:
    """Initialize a conflict exception with a stable error code."""

    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_409_CONFLICT,
    )


class DomainValidationException(DomainException):
  """Represent invalid domain input as an HTTP 422 error."""

  def __init__(
    self,
    message: str = "The request contains invalid data.",
    *,
    error_code: str = "DOMAIN_VALIDATION_ERROR",
    details: ErrorDetails | None = None,
  ) -> None:
    """Initialize a validation exception with field-independent metadata."""

    super().__init__(
      message,
      error_code=error_code,
      status_code=422,
      details=details,
    )


class UnauthorizedException(DomainException):
  """Authentication failed because credentials are missing or invalid."""

  def __init__(self, message: str = "Could not validate credentials") -> None:
    """Initialize an authentication failure response."""

    super().__init__(
      message,
      error_code="UNAUTHORIZED",
      status_code=status.HTTP_401_UNAUTHORIZED,
    )


class ForbiddenException(DomainException):
  """The authenticated user is not allowed to access the resource."""

  def __init__(self, message: str = "Insufficient permissions") -> None:
    """Initialize an authorization failure response."""

    super().__init__(
      message,
      error_code="FORBIDDEN",
      status_code=status.HTTP_403_FORBIDDEN,
    )


class WorkflowValidationException(DomainValidationException):
  """Represent an invalid workflow transition as an HTTP 422 error."""

  def __init__(self, message: str = "Invalid workflow operation.") -> None:
    """Initialize an invalid workflow-transition response."""

    super().__init__(
      message,
      error_code="WORKFLOW_VALIDATION_FAILED",
    )
