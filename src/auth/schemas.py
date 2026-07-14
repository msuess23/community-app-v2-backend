from pydantic import BaseModel, EmailStr, Field, SecretStr

from src.core.validation import MAX_REFRESH_TOKEN_LENGTH, PasswordValue


class TokenResponse(BaseModel):
  access_token: str
  refresh_token: str
  token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
  refresh_token: SecretStr = Field(
    min_length=1,
    max_length=MAX_REFRESH_TOKEN_LENGTH,
  )


class ForgotPasswordRequest(BaseModel):
  email: EmailStr


class ResetPasswordRequest(BaseModel):
  email: EmailStr
  otp: str = Field(pattern=r"^[0-9]{6}$")
  new_password: PasswordValue
