import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import (
  PasswordReset,
  RefreshSession,
  RefreshSessionRevokeReason,
)
from src.auth.repository import AuthRepository
from src.auth.schemas import ResetPasswordRequest, TokenResponse
from src.core.email import send_otp_email
from src.core.exceptions import AuthenticationException, DomainException
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
from src.user.models import User, UserHistory
from src.user.repository import UserRepository
from src.user.schemas import UserCreate


class AuthService:
  """
  Handles authentication, registration, token rotation, and account recovery.

  Access tokens remain short-lived and stateless. Refresh tokens are backed by
  server-side session rows and are replaced after every successful refresh.
  """

  @staticmethod
  async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    """Validate input, create a user, and append the initial audit entry."""
    existing_user = await UserRepository.get_by_email(db, user_data.email)
    if existing_user:
      raise DomainException(
        "Email already registered",
        error_code="EMAIL_EXISTS",
        status_code=400,
      )

    new_user = User(
      email=user_data.email,
      hashed_password=get_password_hash(user_data.password),
      first_name=user_data.first_name,
      last_name=user_data.last_name,
    )

    UserRepository.add(db, new_user)
    await db.flush()

    history_entry = UserHistory(
      user_id=new_user.id,
      email=new_user.email,
      first_name=new_user.first_name,
      last_name=new_user.last_name,
      role=new_user.role,
      changed_by_user_id=new_user.id,
      change_reason="Initial Registration",
    )
    UserRepository.add_history(db, history_entry)

    await db.commit()
    await db.refresh(new_user)
    return new_user

  @staticmethod
  async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
  ) -> TokenResponse:
    """Authenticate a user and create an independent refresh-session family."""
    user = await UserRepository.get_by_email(db, email=email)
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

    await db.commit()

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
        await db.commit()
      raise AuthenticationException("Refresh session is no longer valid")

    if session.expires_at <= now:
      session.revoked_at = now
      session.revoke_reason = RefreshSessionRevokeReason.EXPIRED.value
      await db.commit()
      raise AuthenticationException("Refresh session has expired")

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
      await db.commit()
      raise AuthenticationException("Refresh session is no longer valid")

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
    await db.commit()

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
    """Create a reset OTP without revealing whether an active user exists."""
    user = await UserRepository.get_by_email(db, email)
    if user is None or not user.is_active:
      return

    await AuthRepository.delete_password_resets_by_email(db, email)

    otp_code = "".join(secrets.choice(string.digits) for _ in range(6))
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    reset_record = PasswordReset(
      email=email,
      otp_hash=get_password_hash(otp_code),
      expires_at=expires,
    )

    AuthRepository.add_password_reset(db, reset_record)
    await db.commit()
    background_tasks.add_task(send_otp_email, email, otp_code)

  @staticmethod
  async def reset_password(
    db: AsyncSession,
    data: ResetPasswordRequest,
  ) -> None:
    """Validate the OTP, change the password, and revoke active sessions."""
    reset_record = await AuthRepository.get_password_reset_by_email(
      db,
      data.email,
    )

    if not reset_record:
      raise DomainException("Invalid or expired OTP", status_code=400)

    if reset_record.expires_at < datetime.now(timezone.utc):
      await AuthRepository.delete_password_reset_by_id(db, reset_record.id)
      await db.commit()
      raise DomainException("OTP has expired", status_code=400)

    if not verify_password(data.otp, reset_record.otp_hash):
      raise DomainException("Invalid OTP", status_code=400)

    user = await UserRepository.get_by_email(db, data.email)
    if user is None or not user.is_active:
      raise DomainException("Invalid or expired OTP", status_code=400)

    user.hashed_password = get_password_hash(data.new_password)
    user.auth_version += 1
    UserRepository.add(db, user)

    await AuthRepository.revoke_all_refresh_sessions_for_user(
      db,
      user.id,
      RefreshSessionRevokeReason.PASSWORD_RESET,
    )
    await AuthRepository.delete_password_reset_by_id(db, reset_record.id)
    await db.commit()

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
    await db.commit()
