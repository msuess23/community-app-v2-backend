from typing import Any, Mapping

from fastapi import status


class DomainException(Exception):
  """Base class for expected, client-facing application errors."""

  def __init__(
    self,
    message: str,
    *,
    error_code: str,
    status_code: int,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
  ) -> None:
    super().__init__(message)
    self.message = message
    self.error_code = error_code
    self.status_code = status_code
    self.details = details
    self.headers = dict(headers) if headers else None


class BadRequestException(DomainException):
  def __init__(
    self,
    message: str = "The request could not be processed.",
    *,
    error_code: str = "BAD_REQUEST",
    details: Any = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_400_BAD_REQUEST,
      details=details,
    )


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
    details: Any = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=status.HTTP_409_CONFLICT,
      details=details,
    )


class DomainValidationException(DomainException):
  def __init__(
    self,
    message: str = "The submitted data violates a business rule.",
    *,
    error_code: str = "DOMAIN_VALIDATION_FAILED",
    details: Any = None,
  ) -> None:
    super().__init__(
      message,
      error_code=error_code,
      status_code=422,
      details=details,
    )


class AuthenticationException(DomainException):
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
