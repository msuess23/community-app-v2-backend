from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.schemas import (
  ForgotPasswordRequest,
  LogoutRequest,
  RefreshTokenRequest,
  ResetPasswordRequest,
  TokenResponse,
)
from src.auth.service import AuthService
from src.core.database import get_db
from src.user.models import User
from src.user.schemas import UserCreate, UserResponse


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
  user_data: UserCreate,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Registers a citizen account."""
  return await AuthService.register_user(db, user_data)


@router.post("/login", response_model=TokenResponse)
async def login(
  form_data: OAuth2PasswordRequestForm = Depends(),
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Authenticates an active user and creates a refresh session."""
  return await AuthService.login(db, form_data.username, form_data.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
  request: RefreshTokenRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Rotates a valid refresh token and returns a new token pair."""
  return await AuthService.refresh(db, request.refresh_token)


@router.post("/forgot-password-request")
async def forgot_password_request(
  request: ForgotPasswordRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Creates a development OTP without revealing whether the email exists."""
  await AuthService.request_password_reset(db, str(request.email))
  return {
    "message": "If this email exists, a reset code has been generated."
  }


@router.post("/reset-password")
async def reset_password(
  request: ResetPasswordRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Changes the password using a valid one-time code."""
  await AuthService.reset_password(db, request)
  return {"message": "Password updated successfully."}


@router.post("/logout")
async def logout(
  request: LogoutRequest,
  db: AsyncSession = Depends(get_db, scope="function"),
):
  """Deletes the supplied refresh token. The operation is idempotent."""
  await AuthService.logout(db, request.refresh_token)
  return {"message": "Successfully logged out."}


@router.post("/logout-all")
async def logout_all(
  db: AsyncSession = Depends(get_db, scope="function"),
  current_user: User = Depends(get_current_user),
):
  """Invalidate every refresh session of the authenticated user."""

  await AuthService.logout_all(db, current_user.id)
  return {"message": "Successfully logged out from all devices."}
