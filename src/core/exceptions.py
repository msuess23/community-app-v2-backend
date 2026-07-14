from __future__ import annotations

from typing import Any, Mapping, Sequence

from fastapi import status


ErrorDetails = Sequence[Mapping[str, Any]] | Mapping[str, Any]


class DomainException(Exception):
  """Base class for expected, client-facing domain errors."""

  def __init__(
    self,
    message: str,
    *,
    error_code: str,
    status_code: int,
    details: ErrorDetails | None = None,
    headers: Mapping[str, str] | None = None,
  ) -> None:
    self.message = message
    self.error_code = error_code
    self.status_code = status_code
    self.details = details
    self.headers = dict(headers) if headers else None
    super().__init__(message)


class BadRequestException(DomainException):
  """The request is syntactically valid but cannot be processed as requested."""

  def __init__(
    self,
    message: str = "The request could not be processed.",
    *,
    error_code: str = "BAD_REQUEST",
    details: ErrorDetails | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_400_BAD_REQUEST,
      details=details,
    )


class ResourceNotFoundException(DomainException):
  """A requested domain resource does not exist."""

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
  """The request conflicts with the current state of a resource."""

  def __init__(
    self,
    message: str = "The request conflicts with the current resource state.",
    *,
    error_code: str = "RESOURCE_CONFLICT",
    details: ErrorDetails | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_409_CONFLICT,
      details=details,
    )


class DomainValidationException(DomainException):
  """A domain invariant or business validation rule was violated."""

  def __init__(
    self,
    message: str = "The submitted data violates a business rule.",
    *,
    error_code: str = "DOMAIN_VALIDATION_FAILED",
    details: ErrorDetails | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=422,
      details=details,
    )


class AuthenticationException(DomainException):
  """Authentication credentials are missing, invalid, or no longer usable."""

  def __init__(
    self,
    message: str = "Could not validate credentials.",
    *,
    error_code: str = "AUTHENTICATION_FAILED",
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_401_UNAUTHORIZED,
      headers={"WWW-Authenticate": "Bearer"},
    )


class ForbiddenException(DomainException):
  """An authenticated actor lacks permission for the requested operation."""

  def __init__(
    self,
    message: str = "You are not allowed to perform this action.",
    *,
    error_code: str = "FORBIDDEN",
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_403_FORBIDDEN,
    )


class WorkflowValidationException(DomainValidationException):
  """A ticket or appointment workflow command violates its transition rules."""

  def __init__(self, message: str = "Invalid workflow operation.") -> None:
    super().__init__(
      message,
      error_code="WORKFLOW_VALIDATION_FAILED",
    )


# Temporary compatibility alias for modules outside the current refactoring
# scope. New code should use AuthenticationException explicitly.
UnauthorizedException = AuthenticationException
