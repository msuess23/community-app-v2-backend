import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import PasswordReset, RefreshToken
from src.auth.repository import AuthRepository
from src.auth.schemas import ResetPasswordRequest, TokenResponse
from src.core.config import settings
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  UnauthorizedException,
)
from src.core.security import (
  create_access_token,
  generate_refresh_token,
  get_password_hash,
  hash_token,
  normalize_email,
  verify_password,
)
from src.user.models import User
from src.user.repository import UserRepository
from src.user.schemas import UserCreate


class AuthService:
  """Business logic for login, refresh, logout, registration and password reset."""

  @staticmethod
  async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    email = normalize_email(str(user_data.email))
    existing_user = await UserRepository.get_by_email(db, email)
    if existing_user:
      raise ConflictException(
        "Email already registered",
        error_code="EMAIL_ALREADY_REGISTERED",
      )

    new_user = User(
      email=email,
      hashed_password=get_password_hash(user_data.password),
      first_name=user_data.first_name,
      last_name=user_data.last_name,
    )
    UserRepository.add(db, new_user)
    await db.flush()
    await db.refresh(new_user)
    return new_user

  @staticmethod
  async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
    user = await UserRepository.get_by_email(db, normalize_email(email))
    if (
      user is None
      or not user.is_active
      or not verify_password(password, user.hashed_password)
    ):
      raise UnauthorizedException("Incorrect email or password")

    return await AuthService._create_session(db, user)

  @staticmethod
  async def refresh(db: AsyncSession, refresh_token: str) -> TokenResponse:
    stored_token = await AuthRepository.get_refresh_token_by_hash(
      db,
      hash_token(refresh_token),
    )
    if stored_token is None:
      raise UnauthorizedException("Invalid refresh token")

    if stored_token.expires_at <= datetime.now(timezone.utc):
      raise UnauthorizedException("Refresh token has expired")

    user = await UserRepository.get_by_id(db, stored_token.user_id)
    if user is None or not user.is_active:
      raise UnauthorizedException("Invalid refresh token")

    await AuthRepository.delete_refresh_token_by_hash(db, stored_token.token_hash)
    return await AuthService._create_session(db, user)

  @staticmethod
  async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Deletes the supplied refresh token. Repeated calls are intentionally harmless."""
    await AuthRepository.delete_refresh_token_by_hash(db, hash_token(refresh_token))

  @staticmethod
  async def request_password_reset(db: AsyncSession, email: str) -> None:
    """Creates a short-lived OTP and prints it for the local study environment."""
    normalized_email = normalize_email(email)
    user = await UserRepository.get_by_email(db, normalized_email)
    if user is None or not user.is_active:
      return

    await AuthRepository.delete_password_resets_by_email(db, normalized_email)

    otp_code = "".join(secrets.choice(string.digits) for _ in range(6))
    AuthRepository.add_password_reset(
      db,
      PasswordReset(
        email=normalized_email,
        otp_hash=get_password_hash(otp_code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
      ),
    )
    await db.flush()

    print(f"[DEV] Password reset OTP for {normalized_email}: {otp_code}")

  @staticmethod
  async def reset_password(db: AsyncSession, data: ResetPasswordRequest) -> None:
    normalized_email = normalize_email(str(data.email))
    reset_record = await AuthRepository.get_password_reset_by_email(
      db,
      normalized_email,
    )

    if reset_record is None or reset_record.expires_at <= datetime.now(timezone.utc):
      raise DomainValidationException(
        "Invalid or expired OTP",
        error_code="INVALID_OTP",
      )

    if not verify_password(data.otp, reset_record.otp_hash):
      raise DomainValidationException(
        "Invalid or expired OTP",
        error_code="INVALID_OTP",
      )

    user = await UserRepository.get_by_email(db, normalized_email)
    if user is None or not user.is_active:
      raise DomainValidationException(
        "Invalid or expired OTP",
        error_code="INVALID_OTP",
      )

    user.hashed_password = get_password_hash(data.new_password)
    UserRepository.add(db, user)
    await AuthRepository.delete_refresh_tokens_by_user_id(db, user.id)
    await AuthRepository.delete_password_reset_by_id(db, reset_record.id)
    await db.flush()

  @staticmethod
  async def _create_session(db: AsyncSession, user: User) -> TokenResponse:
    refresh_token = generate_refresh_token()
    AuthRepository.add_refresh_token(
      db,
      RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(
          days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        ),
      ),
    )
    await db.flush()

    return TokenResponse(
      access_token=create_access_token(subject=user.id),
      refresh_token=refresh_token,
    )
