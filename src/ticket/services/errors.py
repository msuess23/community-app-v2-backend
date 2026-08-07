"""Ticket-specific machine-readable workflow errors."""

from src.core.exceptions import ConflictException, DomainValidationException


class TicketActionNotAllowedException(ConflictException):
  """The requested action is not valid for the current ticket projection."""

  def __init__(self, message: str = "The ticket action is no longer available.") -> None:
    """Initialize a stable conflict response for a stale or invalid action."""

    super().__init__(message, error_code="TICKET_ACTION_NOT_ALLOWED")


class TicketTargetNotEligibleException(DomainValidationException):
  """The selected target never satisfies the action's role constraints."""

  def __init__(self, message: str = "The selected workflow target is not eligible.") -> None:
    """Initialize a validation error for a target with an invalid role."""

    super().__init__(message, error_code="TICKET_TARGET_NOT_ELIGIBLE")


class TicketTargetUnavailableException(ConflictException):
  """A formerly selectable target is missing or inactive at command time."""

  def __init__(self, message: str = "The selected workflow target is no longer available.") -> None:
    """Initialize a conflict for a target removed after option loading."""

    super().__init__(message, error_code="TICKET_TARGET_NO_LONGER_AVAILABLE")


class TicketSelfTargetException(DomainValidationException):
  """The workflow action may not target the actor themselves."""

  def __init__(self, message: str = "A workflow action cannot target the current user.") -> None:
    """Initialize a validation error for prohibited self-targeting."""

    super().__init__(message, error_code="TICKET_SELF_TARGET_NOT_ALLOWED")


class TicketTargetAlreadySelectedException(ConflictException):
  """The selected target already owns the requested workflow responsibility."""

  def __init__(self, message: str = "The selected workflow target is already assigned.") -> None:
    """Initialize a conflict for a no-op responsibility assignment."""

    super().__init__(message, error_code="TICKET_TARGET_ALREADY_SELECTED")


class TicketCompletionOutcomeNotAllowedException(DomainValidationException):
  """The selected terminal outcome is not available to the actor's role."""

  def __init__(self) -> None:
    """Initialize a validation error for a role-restricted outcome."""

    super().__init__(
      "The selected completion outcome is not allowed for this role.",
      error_code="TICKET_COMPLETION_OUTCOME_NOT_ALLOWED",
    )


class TicketProjectionVersionMismatchException(ConflictException):
  """The current projection version differs from the stored event stream."""

  def __init__(self) -> None:
    """Initialize a conflict that protects append-only stream consistency."""

    super().__init__(
      "The ticket projection is inconsistent with its event stream.",
      error_code="TICKET_PROJECTION_VERSION_MISMATCH",
    )
