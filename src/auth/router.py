from fastapi import APIRouter, BackgroundTasks, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer

from src.core.config import settings
from src.core.database import get_db
from src.core.security import (
  create_access_token,
  create_refresh_token,
  verify_and_update_password,
)
from src.core.exceptions import UnauthorizedException

from src.user.repository import UserRepository
from src.auth.service import AuthService
from src.user.schemas import UserCreate, UserResponse
from src.auth.schemas import TokenResponse, ForgotPasswordRequest, ResetPasswordRequest

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.BASE_URL}/auth/login")
router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
  user_data: UserCreate, 
  db: AsyncSession = Depends(get_db)
):
  """Registers a new user."""
  return await AuthService.register_user(db, user_data)


@router.post("/login", response_model=TokenResponse)
async def login(
  form_data: OAuth2PasswordRequestForm = Depends(),
  db: AsyncSession = Depends(get_db)
):
  """Authenticates a user and returns JWT tokens."""
  user = await UserRepository.get_by_email(db, email=form_data.username)
  if not user:
    raise UnauthorizedException("Incorrect email or password")

  password_valid, updated_hash = verify_and_update_password(
    form_data.password,
    user.hashed_password,
  )
  if not password_valid or not user.is_active:
    raise UnauthorizedException("Incorrect email or password")

  if updated_hash is not None:
    user.hashed_password = updated_hash
    await db.commit()

  return TokenResponse(
    access_token=create_access_token(
      subject=user.id,
      auth_version=user.auth_version,
    ),
    refresh_token=create_refresh_token(
      subject=user.id,
      auth_version=user.auth_version,
    ),
  )


@router.post("/forgot-password-request")
async def forgot_password_request(
  request: ForgotPasswordRequest, 
  background_tasks: BackgroundTasks,
  db: AsyncSession = Depends(get_db)
):
  """Triggers an OTP email if the user exists."""
  await AuthService.request_password_reset(db, request.email, background_tasks)
  return {"message": "If this email exists, an OTP has been sent."}

@router.post("/reset-password")
async def reset_password(
  request: ResetPasswordRequest,
  db: AsyncSession = Depends(get_db)
):
  """Resets the password using a valid OTP."""
  await AuthService.reset_password(db, request)
  return {"message": "Password updated successfully."}


@router.post("/logout")
async def logout(
  refresh_token: str | None = Body(None, embed=True),
  token: str = Depends(oauth2_scheme),
  db: AsyncSession = Depends(get_db)
):
  """
  Invalidates the current access token (and optionally the refresh token).
  Safe to call multiple times with the same token.
  """
  await AuthService.logout(db, access_token=token, refresh_token=refresh_token)
  return {"message": "Successfully logged out."}