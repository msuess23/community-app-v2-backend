from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.core.security import ensure_bcrypt_compatible, normalize_email


class TokenResponse(BaseModel):
  access_token: str
  refresh_token: Optional[str] = None
  token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
  refresh_token: str = Field(..., min_length=32, max_length=512)


class LogoutRequest(BaseModel):
  refresh_token: str = Field(..., min_length=32, max_length=512)


class ForgotPasswordRequest(BaseModel):
  email: EmailStr

  @field_validator("email")
  @classmethod
  def normalize_email_value(cls, value: EmailStr) -> str:
    return normalize_email(str(value))


class ResetPasswordRequest(BaseModel):
  email: EmailStr
  otp: str = Field(..., pattern=r"^[0-9]{6}$")
  new_password: str = Field(..., min_length=8, max_length=128)

  @field_validator("email")
  @classmethod
  def normalize_email_value(cls, value: EmailStr) -> str:
    return normalize_email(str(value))

  @field_validator("new_password")
  @classmethod
  def validate_password_bytes(cls, value: str) -> str:
    return ensure_bcrypt_compatible(value)
