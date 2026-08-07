from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.core.request_models import StrictRequestModel
from src.core.security import ensure_bcrypt_compatible, normalize_email


class TokenResponse(BaseModel):
  """Return an access and refresh token pair after authentication."""

  access_token: str
  refresh_token: Optional[str] = None
  token_type: str = "bearer"


class RefreshTokenRequest(StrictRequestModel):
  """Validate a refresh token rotation request."""

  refresh_token: str = Field(..., min_length=32, max_length=512)


class LogoutRequest(StrictRequestModel):
  """Validate a request that revokes one refresh token."""

  refresh_token: str = Field(..., min_length=32, max_length=512)


class ForgotPasswordRequest(StrictRequestModel):
  """Validate an email address for password recovery."""

  email: EmailStr

  @field_validator("email")
  @classmethod
  def normalize_email_value(cls, value: EmailStr) -> str:
    """Normalize the recovery email before validation."""

    return normalize_email(str(value))


class ResetPasswordRequest(StrictRequestModel):
  """Validate an OTP-backed password reset request."""

  email: EmailStr
  otp: str = Field(..., pattern=r"^[0-9]{6}$")
  new_password: str = Field(..., min_length=8, max_length=128)

  @field_validator("email")
  @classmethod
  def normalize_email_value(cls, value: EmailStr) -> str:
    """Normalize the account email before OTP verification."""

    return normalize_email(str(value))

  @field_validator("new_password")
  @classmethod
  def validate_password_bytes(cls, value: str) -> str:
    """Reject passwords that exceed the bcrypt byte limit."""

    return ensure_bcrypt_compatible(value)
