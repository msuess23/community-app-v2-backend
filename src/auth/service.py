import secrets
import string
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_password_hash, verify_password
from src.core.email import send_otp_email
from src.core.exceptions import DomainException
from src.user.models import User, UserHistory
from src.auth.models import PasswordReset, BlacklistedToken
from src.user.schemas import UserCreate
from src.auth.schemas import ResetPasswordRequest
from src.user.repository import UserRepository
from src.auth.repository import AuthRepository

class AuthService:
  """
  Handles business logic for authentication, registration, and account recovery.
  Delegates all database interactions to the respective repositories.
  """
  
  @staticmethod
  async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    """
    Validates input, hashes the password, and stages a new user and audit trail 
    for database insertion.
    """
    existing_user = await UserRepository.get_by_email(db, user_data.email)
    if existing_user:
      raise DomainException("Email already registered", error_code="EMAIL_EXISTS", status_code=400)
    
    new_user = User(
      email=user_data.email,
      hashed_password=get_password_hash(user_data.password),
      first_name=user_data.first_name,
      last_name=user_data.last_name
    )
    
    UserRepository.add(db, new_user)
    
    # Flush to generate the new user's UUID for the history entry without committing the transaction
    await db.flush()
    
    history_entry = UserHistory(
      user_id=new_user.id,
      email=new_user.email,
      first_name=new_user.first_name,
      last_name=new_user.last_name,
      role=new_user.role,
      changed_by_user_id=new_user.id,
      change_reason="Initial Registration"
    )
    
    UserRepository.add_history(db, history_entry)
    
    # Complete the unit of work
    await db.commit()
    await db.refresh(new_user)
    
    return new_user

  @staticmethod
  async def request_password_reset(db: AsyncSession, email: str, background_tasks: BackgroundTasks) -> None:
    """
    Generates a secure OTP for password reset and triggers an email task.
    Returns silently if the email does not exist to prevent user enumeration.
    """
    user = await UserRepository.get_by_email(db, email)
    if not user:
      return
    
    # Invalidate previous OTPs for this email
    await AuthRepository.delete_password_resets_by_email(db, email)
    
    otp_code = ''.join(secrets.choice(string.digits) for _ in range(6))
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    reset_record = PasswordReset(
      email=email,
      otp_hash=get_password_hash(otp_code),
      expires_at=expires
    )
    
    AuthRepository.add_password_reset(db, reset_record)
    await db.commit()
    
    # Delegate email sending to background process
    background_tasks.add_task(send_otp_email, email, otp_code)

  @staticmethod
  async def reset_password(db: AsyncSession, data: ResetPasswordRequest) -> None:
    """
    Validates the OTP and applies the new password to the user account.
    """
    reset_record = await AuthRepository.get_password_reset_by_email(db, data.email)
    
    if not reset_record:
      raise DomainException("Invalid or expired OTP", status_code=400)
      
    if reset_record.expires_at < datetime.now(timezone.utc):
      await AuthRepository.delete_password_reset_by_id(db, reset_record.id)
      await db.commit()
      raise DomainException("OTP has expired", status_code=400)
      
    if not verify_password(data.otp, reset_record.otp_hash):
      raise DomainException("Invalid OTP", status_code=400)
    
    user = await UserRepository.get_by_email(db, data.email)
    if not user:
      raise DomainException("User not found", status_code=404)
      
    user.hashed_password = get_password_hash(data.new_password)
    UserRepository.add(db, user)
    
    # Cleanup used OTP
    await AuthRepository.delete_password_reset_by_id(db, reset_record.id)
    await db.commit()

  @staticmethod
  async def logout(db: AsyncSession, access_token: str, refresh_token: Optional[str] = None) -> None:
    """
    Invalidates tokens by adding them to the blacklist.
    Silently ignores tokens that are already blacklisted.
    """
    # Check and blacklist access token
    is_access_blacklisted = await AuthRepository.is_token_blacklisted(db, access_token)
    if not is_access_blacklisted:
      AuthRepository.add_blacklisted_token(db, BlacklistedToken(token=access_token))
    
    # Check and blacklist refresh token if provided
    if refresh_token:
      is_refresh_blacklisted = await AuthRepository.is_token_blacklisted(db, refresh_token)
      if not is_refresh_blacklisted:
        AuthRepository.add_blacklisted_token(db, BlacklistedToken(token=refresh_token))
        
    await db.commit()