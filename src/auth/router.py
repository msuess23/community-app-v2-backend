from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import (
  ForgotPasswordRequest,
  RefreshTokenRequest,
  ResetPasswordRequest,
  TokenResponse,
)
from src.auth.service import AuthService
from src.core.database import get_db
from src.user.schemas import UserCreate, UserResponse


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
  user_data: UserCreate,
  db: AsyncSession = Depends(get_db),
):
  """Registers a new user."""
  return await AuthService.register_user(db, user_data)


@router.post("/login", response_model=TokenResponse)
async def login(
  form_data: OAuth2PasswordRequestForm = Depends(),
  db: AsyncSession = Depends(get_db),
):
  """Authenticates a user and opens a new refresh-session family."""
  return await AuthService.login(
    db,
    email=form_data.username,
    password=form_data.password,
  )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
  request: RefreshTokenRequest,
  db: AsyncSession = Depends(get_db),
):
  """Rotates a refresh token and returns a fresh access/refresh pair."""
  return await AuthService.refresh_tokens(
    db,
    request.refresh_token.get_secret_value(),
  )


@router.post("/forgot-password-request")
async def forgot_password_request(
  request: ForgotPasswordRequest,
  background_tasks: BackgroundTasks,
  db: AsyncSession = Depends(get_db),
):
  """Triggers an OTP email if an active user exists."""
  await AuthService.request_password_reset(
    db,
    request.email,
    background_tasks,
  )
  return {"message": "If this email exists, an OTP has been sent."}


@router.post("/reset-password")
async def reset_password(
  request: ResetPasswordRequest,
  db: AsyncSession = Depends(get_db),
):
  """Resets the password using a valid OTP."""
  await AuthService.reset_password(db, request)
  return {"message": "Password updated successfully."}


@router.post("/logout")
async def logout(
  request: RefreshTokenRequest,
  db: AsyncSession = Depends(get_db),
):
  """
  Revokes the complete refresh-token family for the current client session.

  The endpoint is intentionally idempotent and does not reveal whether the
  submitted token existed. The client must also discard its access token.
  """
  await AuthService.logout(
    db,
    request.refresh_token.get_secret_value(),
  )
  return {"message": "Successfully logged out."}
