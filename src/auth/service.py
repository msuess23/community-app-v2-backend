import secrets
import string
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from src.core.security import get_password_hash, verify_password
from src.core.email import send_otp_email
from src.core.exceptions import DomainException
from src.user.repository import get_user_by_email, create_user
from src.auth.models import PasswordReset
from src.user.schemas import UserCreate
from src.auth.schemas import ResetPasswordRequest

class AuthService:
  """
  Handles business logic for authentication and account recovery.
  """
  
  @staticmethod
  async def register_user(db: AsyncSession, user_data: UserCreate):
    existing = await get_user_by_email(db, user_data.email)
    if existing:
      raise DomainException("Email already registered", error_code="EMAIL_EXISTS", status_code=400)
    
    db_user_data = {
      "email": user_data.email,
      "hashed_password": get_password_hash(user_data.password),
      "first_name": user_data.first_name,
      "last_name": user_data.last_name
    }
    return await create_user(db, db_user_data)

  @staticmethod
  async def request_password_reset(db: AsyncSession, email: str, background_tasks: BackgroundTasks):
    user = await get_user_by_email(db, email)
    
    # Return immediately to prevent email enumeration
    if not user:
      return
    
    # Invalidate old OTPs
    await db.execute(delete(PasswordReset).where(PasswordReset.email == email))
    
    # Generate and store new OTP
    otp_code = ''.join(secrets.choice(string.digits) for _ in range(6))
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    reset_record = PasswordReset(
      email=email,
      otp_hash=get_password_hash(otp_code),
      expires_at=expires
    )
    db.add(reset_record)
    await db.commit()
    
    # Send email in background
    background_tasks.add_task(send_otp_email, email, otp_code)

  @staticmethod
  async def reset_password(db: AsyncSession, data: ResetPasswordRequest):
    result = await db.execute(select(PasswordReset).where(PasswordReset.email == data.email))
    reset_record = result.scalar_one_or_none()
    
    if not reset_record:
      raise DomainException("Invalid or expired OTP", status_code=400)
      
    if reset_record.expires_at < datetime.now(timezone.utc):
      await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_record.id))
      await db.commit()
      raise DomainException("OTP has expired", status_code=400)
      
    if not verify_password(data.otp, reset_record.otp_hash):
      raise DomainException("Invalid OTP", status_code=400)
    
    # Update password
    user = await get_user_by_email(db, data.email)
    if not user:
      raise DomainException("User not found", status_code=404)
      
    user.hashed_password = get_password_hash(data.new_password)
    db.add(user)
    
    # Cleanup OTP
    await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_record.id))
    await db.commit()