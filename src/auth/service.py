import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import (
  RefreshSession,
  RefreshSessionRevokeReason,
)
from src.auth.repository import AuthRepository
from src.auth.schemas import ResetPasswordRequest, TokenResponse
from src.core.config import settings
from src.core.email import send_otp_email, send_password_changed_email
from src.core.database import commit_and_raise
from src.core.exceptions import (
  AuthenticationException,
  BadRequestException,
  ConflictException,
)
from src.core.normalization import normalize_email
from src.core.security import (
  TokenType,
  TokenValidationError,
  create_access_token,
  decode_token,
  get_password_hash,
  hash_token,
  issue_refresh_token,
  token_hash_matches,
  verify_and_update_password,
  verify_password,
)
from src.core.validation import has_valid_password_length
from src.user.audit import build_user_history
from src.user.models import User
from src.user.repository import UserRepository
from src.user.schemas import UserCreate


_INVALID_RESET_MESSAGE = "Invalid or expired password-reset code"


class AuthService:
  """
  Handles authentication, registration, token rotation, and account recovery.

  Access tokens remain short-lived and stateless. Refresh tokens are backed by
  server-side session rows and are replaced after every successful refresh.
  """

  @staticmethod
  async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    """Validate input, create a citizen, and append the initial version."""
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
    )

    UserRepository.add(db, new_user)
    await db.flush()
    UserRepository.add_history(
      db,
      build_user_history(
        new_user,
        actor_id=new_user.id,
        change_reason="Initial registration",
        valid_from=now,
      ),
    )

    await db.flush()
    return new_user

  @staticmethod
  async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
  ) -> TokenResponse:
    """Authenticate a user and create an independent refresh-session family."""
    # OAuth2PasswordRequestForm is not a Pydantic request model. Enforce the
    # same maximum here before handing untrusted input to Argon2/bcrypt.
    if not has_valid_password_length(password):
      raise AuthenticationException("Incorrect email or password")

    user = await UserRepository.get_by_email(db, email=normalize_email(email))
    if user is None:
      raise AuthenticationException("Incorrect email or password")

    password_valid, updated_hash = verify_and_update_password(
      password,
      user.hashed_password,
    )
    if not password_valid or not user.is_active:
      raise AuthenticationException("Incorrect email or password")

    if updated_hash is not None:
      user.hashed_password = updated_hash

    family_id = uuid.uuid4()
    refresh_token = issue_refresh_token(
      subject=user.id,
      auth_version=user.auth_version,
    )
    access_token = create_access_token(
      subject=user.id,
      auth_version=user.auth_version,
    )
    AuthRepository.add_refresh_session(
      db,
      RefreshSession(
        id=refresh_token.jti,
        user_id=user.id,
        family_id=family_id,
        token_hash=hash_token(refresh_token.value),
        expires_at=refresh_token.expires_at,
      ),
    )


    return TokenResponse(
      access_token=access_token,
      refresh_token=refresh_token.value,
    )

  @staticmethod
  async def refresh_tokens(
    db: AsyncSession,
    refresh_token: str,
  ) -> TokenResponse:
    """
    Rotate a refresh token atomically and issue a fresh token pair.

    Reuse of a token that was already rotated revokes the complete session
    family. Other login sessions of the same user remain unaffected.
    """
    try:
      claims = decode_token(
        refresh_token,
        expected_type=TokenType.REFRESH,
      )
    except TokenValidationError as exc:
      raise AuthenticationException("Invalid refresh token") from exc

    session = await AuthRepository.get_refresh_session_for_update(
      db,
      claims.jti,
    )
    if (
      session is None
      or session.user_id != claims.sub
      or not token_hash_matches(refresh_token, session.token_hash)
    ):
      raise AuthenticationException("Invalid refresh token")

    now = datetime.now(timezone.utc)

    if session.revoked_at is not None:
      if session.revoke_reason == RefreshSessionRevokeReason.ROTATED.value:
        await AuthRepository.revoke_refresh_session_family(
          db,
          session.family_id,
          RefreshSessionRevokeReason.REUSE_DETECTED,
          revoked_at=now,
        )
        commit_and_raise(
          AuthenticationException("Refresh session is no longer valid")
        )
      raise AuthenticationException("Refresh session is no longer valid")

    if session.expires_at <= now:
      session.revoked_at = now
      session.revoke_reason = RefreshSessionRevokeReason.EXPIRED.value
      commit_and_raise(
        AuthenticationException("Refresh session has expired")
      )

    user = await db.get(User, claims.sub)
    if (
      user is None
      or not user.is_active
      or user.auth_version != claims.ver
    ):
      await AuthRepository.revoke_refresh_session_family(
        db,
        session.family_id,
        RefreshSessionRevokeReason.AUTH_VERSION_CHANGED,
        revoked_at=now,
      )
      commit_and_raise(
        AuthenticationException("Refresh session is no longer valid")
      )

    # Keep the family's original absolute expiry. Rotation does not create an
    # indefinitely renewable login session.
    replacement_token = issue_refresh_token(
      subject=user.id,
      auth_version=user.auth_version,
      expires_at=session.expires_at,
    )
    replacement_session = RefreshSession(
      id=replacement_token.jti,
      user_id=user.id,
      family_id=session.family_id,
      token_hash=hash_token(replacement_token.value),
      expires_at=replacement_token.expires_at,
    )
    AuthRepository.add_refresh_session(db, replacement_session)

    # Insert the replacement before linking the old row to it. The surrounding
    # transaction still guarantees all-or-nothing behavior.
    await db.flush()

    session.last_used_at = now
    session.revoked_at = now
    session.revoke_reason = RefreshSessionRevokeReason.ROTATED.value
    session.replaced_by_id = replacement_session.id

    # Create the full response before committing. If token creation fails, the
    # transaction can still roll back instead of consuming the old session.
    access_token = create_access_token(
      subject=user.id,
      auth_version=user.auth_version,
    )
    return TokenResponse(
      access_token=access_token,
      refresh_token=replacement_token.value,
    )

  @staticmethod
  async def request_password_reset(
    db: AsyncSession,
    email: str,
    background_tasks: BackgroundTasks,
  ) -> None:
    """
    Create or rotate a reset OTP without revealing account existence.

    The database upsert enforces one challenge per user and a per-account
    cooldown even when multiple requests arrive concurrently.
    """
    user = await UserRepository.get_by_email(db, normalize_email(email))
    if user is None or not user.is_active:
      return

    now = datetime.now(timezone.utc)
    cooldown_before = (
      now
      - timedelta(
        seconds=settings.PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS,
      )
    )

    # Avoid an unnecessary Argon2 hash for repeated requests that are already
    # inside the cooldown. The subsequent UPSERT still enforces the rule
    # atomically and closes the race between this fast-path check and INSERT.
    existing_reset = await AuthRepository.get_password_reset_by_user_id(
      db,
      user.id,
    )
    if (
      existing_reset is not None
      and existing_reset.requested_at > cooldown_before
    ):
      return

    otp_code = "".join(secrets.choice(string.digits) for _ in range(6))
    accepted = await AuthRepository.upsert_password_reset(
      db,
      user_id=user.id,
      otp_hash=get_password_hash(otp_code),
      expires_at=(
        now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
      ),
      requested_at=now,
      cooldown_before=cooldown_before,
    )
    if accepted:
      background_tasks.add_task(send_otp_email, user.email, otp_code)

  @staticmethod
  async def reset_password(
    db: AsyncSession,
    data: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
  ) -> None:
    """
    Atomically validate and consume an OTP, then revoke all login sessions.

    All failure modes intentionally use the same public error response to avoid
    disclosing whether an account or a usable reset challenge exists.
    """
    user = await UserRepository.get_by_email_for_update(
      db,
      normalize_email(data.email),
    )
    if user is None or not user.is_active:
      raise AuthService._invalid_password_reset()

    reset_record = await AuthRepository.get_password_reset_for_update(
      db,
      user.id,
    )
    now = datetime.now(timezone.utc)

    if reset_record is None:
      raise AuthService._invalid_password_reset()

    if reset_record.expires_at <= now:
      await AuthRepository.delete_password_reset_by_id(db, reset_record.id)
      commit_and_raise(AuthService._invalid_password_reset())

    if reset_record.failed_attempts >= settings.PASSWORD_RESET_MAX_ATTEMPTS:
      raise AuthService._invalid_password_reset()

    if not verify_password(data.otp, reset_record.otp_hash):
      reset_record.failed_attempts += 1
      commit_and_raise(AuthService._invalid_password_reset())

    user.hashed_password = get_password_hash(data.new_password)
    user.auth_version += 1

    await AuthRepository.revoke_all_refresh_sessions_for_user(
      db,
      user.id,
      RefreshSessionRevokeReason.PASSWORD_RESET,
      revoked_at=now,
    )
    await AuthRepository.delete_password_reset_by_id(db, reset_record.id)

    background_tasks.add_task(send_password_changed_email, user.email)

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
    """Revoke a refresh-token family without persisting bearer tokens."""
    try:
      claims = decode_token(
        refresh_token,
        expected_type=TokenType.REFRESH,
      )
    except TokenValidationError:
      return

    session = await AuthRepository.get_refresh_session_for_update(
      db,
      claims.jti,
    )
    if (
      session is None
      or session.user_id != claims.sub
      or not token_hash_matches(refresh_token, session.token_hash)
    ):
      return

    await AuthRepository.revoke_refresh_session_family(
      db,
      session.family_id,
      RefreshSessionRevokeReason.LOGOUT,
    )
