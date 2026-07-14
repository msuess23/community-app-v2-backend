from pydantic import BaseModel, Field, SecretStr

from src.core.validation import MAX_REFRESH_TOKEN_LENGTH, PasswordValue
from src.user.schemas import NormalizedEmail


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
  email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
  email: NormalizedEmail
  otp: str = Field(pattern=r"^[0-9]{6}$")
  new_password: PasswordValue
