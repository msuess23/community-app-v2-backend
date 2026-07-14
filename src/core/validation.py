from typing import Annotated

from pydantic import Field


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_REFRESH_TOKEN_LENGTH = 4096

PasswordValue = Annotated[
  str,
  Field(
    min_length=MIN_PASSWORD_LENGTH,
    max_length=MAX_PASSWORD_LENGTH,
    description=(
      f"Password must contain between {MIN_PASSWORD_LENGTH} and "
      f"{MAX_PASSWORD_LENGTH} characters"
    ),
  ),
]


def has_valid_password_length(password: str) -> bool:
  """Reject pathological login inputs before invoking the password hasher."""
  return MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH
