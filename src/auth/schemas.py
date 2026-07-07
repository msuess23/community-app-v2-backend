from pydantic import BaseModel, EmailStr
from typing import Optional

class TokenResponse(BaseModel):
  access_token: str
  refresh_token: Optional[str] = None
  token_type: str = "bearer"

class ForgotPasswordRequest(BaseModel):
  email: EmailStr

class ResetPasswordRequest(BaseModel):
  email: EmailStr
  otp: str
  new_password: str