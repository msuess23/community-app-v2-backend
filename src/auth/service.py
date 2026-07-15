import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RefreshSession
from src.auth.repository import AuthRepository
from src.auth.schemas import ResetPasswordRequest, TokenResponse
from src.core.config import settings
from src.core.exceptions import (
  AuthenticationException,
  BadRequestException,
  ConflictException,
)
from src.core.normalization import normalize_email
from src.core.security import (
  create_access_token,
  create_refresh_token,
  get_password_hash,
  hash_token,
  verify_password,
)
from src.core.validation import has_valid_password_length
from src.user.models import User
from src.user.repository import UserRepository
from src.user.schemas import UserCreate


_INVALID_RESET_MESSAGE = "Invalid or expired password-reset code"


class AuthService:
  """Authentication, simple refresh-token rotation, and development OTP reset."""

  @staticmethod
  async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    """Validate input and create a citizen account."""
    email = normalize_email(user_data.email)
    existing_user = await UserRepository.get_by_email(db, email)
    if existing_user:
      raise ConflictException(
        "Email already registered",
        error_code="EMAIL_ALREADY_REGISTERED",
      )

    now = datetime.now(timezone.utc)
    new_user = User(
      email=email,
      hashed_password=get_password_hash(user_data.password),
      first_name=user_data.first_name,
      last_name=user_data.last_name,
      created_at=now,
      updated_at=now,
    )

    UserRepository.add(db, new_user)
    await db.flush()
    return new_user

  @staticmethod
  async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
  ) -> TokenResponse:
    """Authenticate a user and create one refresh session."""
    if not has_valid_password_length(password):
      raise AuthenticationException("Incorrect email or password")

    user = await UserRepository.get_by_email(db, email=normalize_email(email))
    if user is None:
      raise AuthenticationException("Incorrect email or password")

    if not verify_password(password, user.hashed_password) or not user.is_active:
      raise AuthenticationException("Incorrect email or password")

    refresh_token = create_refresh_token()
    AuthRepository.add_refresh_session(
      db,
      RefreshSession(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=(
          datetime.now(timezone.utc)
          + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        ),
      ),
    )

    return TokenResponse(
      access_token=create_access_token(
        subject=user.id,
        auth_version=user.auth_version,
      ),
      refresh_token=refresh_token,
    )

  @staticmethod
  async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
  ) -> TokenResponse:
    """Replace a valid refresh token with a new token and access token."""
    session = await AuthRepository.get_refresh_session_by_hash(
      db,
      hash_token(refresh_token),
    )
    now = datetime.now(timezone.utc)
    if session is None or session.expires_at <= now:
      raise AuthenticationException("Invalid or expired refresh token")

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
      raise AuthenticationException("Invalid or expired refresh token")

    new_refresh_token = create_refresh_token()
    await AuthRepository.delete_refresh_session(db, session.id)
    AuthRepository.add_refresh_session(
      db,
      RefreshSession(
        user_id=user.id,
        token_hash=hash_token(new_refresh_token),
        expires_at=(
          now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        ),
      ),
    )

    return TokenResponse(
      access_token=create_access_token(
        subject=user.id,
        auth_version=user.auth_version,
      ),
      refresh_token=new_refresh_token,
    )

  @staticmethod
  async def request_password_reset(
    db: AsyncSession,
    email: str,
  ) -> None:
    """Create a short-lived OTP and print it for local study/demo use."""
    user = await UserRepository.get_by_email(db, normalize_email(email))
    if user is None or not user.is_active:
      return

    now = datetime.now(timezone.utc)
    otp_code = "".join(secrets.choice(string.digits) for _ in range(6))
    await AuthRepository.save_password_reset(
      db,
      user_id=user.id,
      otp_hash=get_password_hash(otp_code),
      expires_at=(
        now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
      ),
      requested_at=now,
    )

    # Intentional development-only delivery mechanism for this study project.
    print(f"[DEV] Password reset OTP for {user.email}: {otp_code}")

  @staticmethod
  async def reset_password(
    db: AsyncSession,
    data: ResetPasswordRequest,
  ) -> None:
    """Validate the latest OTP once and replace the user's password."""
    user = await UserRepository.get_by_email(
      db,
      normalize_email(data.email),
    )
    if user is None or not user.is_active:
      raise AuthService._invalid_password_reset()

    reset_record = await AuthRepository.get_password_reset_by_user_id(
      db,
      user.id,
    )
    now = datetime.now(timezone.utc)
    if (
      reset_record is None
      or reset_record.expires_at <= now
      or not verify_password(data.otp, reset_record.otp_hash)
    ):
      raise AuthService._invalid_password_reset()

    user.hashed_password = get_password_hash(data.new_password)
    user.auth_version += 1
    await AuthRepository.delete_all_refresh_sessions_for_user(db, user.id)
    await AuthRepository.delete_password_reset_by_id(db, reset_record.id)

  @staticmethod
  def _invalid_password_reset() -> BadRequestException:
    return BadRequestException(
      _INVALID_RESET_MESSAGE,
      error_code="PASSWORD_RESET_INVALID",
    )

  @staticmethod
  async def logout(
    db: AsyncSession,
    refresh_token: str,
  ) -> None:
    """Delete the submitted refresh session; repeated calls remain harmless."""
    session = await AuthRepository.get_refresh_session_by_hash(
      db,
      hash_token(refresh_token),
    )
    if session is not None:
      await AuthRepository.delete_refresh_session(db, session.id)
