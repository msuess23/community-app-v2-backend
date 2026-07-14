from fastapi import Request, status
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

class DomainException(Exception):
  """
  Base class for all custom domain exceptions.
  Ensures a consistent error contract across the application.
  """
  def __init__(
    self, 
    message: str, 
    error_code: str = "INTERNAL_SERVER_ERROR", 
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    details: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None
  ):
    self.message = message
    self.error_code = error_code
    self.status_code = status_code
    self.details = details
    self.headers = headers
    super().__init__(self.message)

class ResourceNotFoundException(DomainException):
  """Thrown when a database entity (User, Ticket, etc.) does not exist."""
  def __init__(self, message: str = "The requested resource was not found."):
    super().__init__(
      message=message, 
      error_code="RESOURCE_NOT_FOUND", 
      status_code=status.HTTP_404_NOT_FOUND
    )

class AuthenticationException(DomainException):
  """Thrown when authentication credentials are missing or invalid."""
  def __init__(self, message: str = "Could not validate credentials."):
    super().__init__(
      message=message,
      error_code="AUTHENTICATION_FAILED",
      status_code=status.HTTP_401_UNAUTHORIZED,
      headers={"WWW-Authenticate": "Bearer"}
    )


class ForbiddenException(DomainException):
  """Thrown when an authenticated user lacks the required permission."""
  def __init__(self, message: str = "You are not allowed to perform this action."):
    super().__init__(
      message=message,
      error_code="FORBIDDEN",
      status_code=status.HTTP_403_FORBIDDEN
    )


# Temporary compatibility alias for modules that have not yet been refactored.
UnauthorizedException = AuthenticationException

class WorkflowValidationException(DomainException):
  """Thrown when a ticket/appointment workflow operation violates business rules."""
  def __init__(self, message: str = "Invalid workflow operation."):
    super().__init__(
      message=message,
      error_code="WORKFLOW_VALIDATION_FAILED",
      status_code=status.HTTP_400_BAD_REQUEST
    )

# --- Global Exception Handlers ---

async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
  """
  Catches all DomainExceptions and formats them into a standard JSON payload.
  This handler will be registered in main.py.
  """
  content = {
    "error_code": exc.error_code,
    "message": exc.message
  }
  
  if exc.details:
    content["details"] = exc.details
    
  return JSONResponse(
    status_code=exc.status_code,
    content=content,
    headers=exc.headers
  )