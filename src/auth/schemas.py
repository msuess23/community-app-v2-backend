from pydantic import BaseModel, EmailStr, Field, SecretStr


class TokenResponse(BaseModel):
  access_token: str
  refresh_token: str
  token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
  refresh_token: SecretStr = Field(min_length=1)


class ForgotPasswordRequest(BaseModel):
  email: EmailStr


class ResetPasswordRequest(BaseModel):
  email: EmailStr
  otp: str
  new_password: str
