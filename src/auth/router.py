from fastapi import APIRouter, Depends, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm
import jwt

from src.auth.models import PasswordReset
from src.core.email import send_otp_email
from src.core.config import settings
from src.core.database import get_db
from src.core.security import verify_password, create_access_token, create_refresh_token, get_password_hash
from src.user.repository import get_user_by_email, create_user
from src.core.exceptions import UnauthorizedException, DomainException

router = APIRouter()

@router.post("/login")
async def login(
  form_data: OAuth2PasswordRequestForm = Depends(),
  db: AsyncSession = Depends(get_db)
):
  # 1. Fetch user by email
  user = await get_user_by_email(db, email=form_data.username)
  
  # 2. Verify credentials
  if not user or not verify_password(form_data.password, user.hashed_password):
    raise UnauthorizedException("Incorrect email or password")
  
  # 3. Create BOTH tokens
  access_token = create_access_token(subject=user.id)
  refresh_token = create_refresh_token(subject=user.id)
  
  return {
    "access_token": access_token,
    "refresh_token": refresh_token,
    "token_type": "bearer"
  }

@router.post("/refresh")
async def refresh_token(
  refresh_token: str = Body(..., embed=True),
  db: AsyncSession = Depends(get_db)
):
  """
  Takes a valid refresh token and returns a new access token.
  """
  try:
    # 1. Validate the refresh token
    payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])
    
    # 2. Ensure it's actually a refresh token
    if payload.get("type") != "refresh":
      raise UnauthorizedException("Invalid token type")
      
    user_id = payload.get("sub")
    if not user_id:
      raise UnauthorizedException("Invalid token payload")
      
  except jwt.PyJWTError:
    raise UnauthorizedException("Could not validate credentials")

  # 3. Issue a new access token
  new_access_token = create_access_token(subject=user_id)
  
  return {
    "access_token": new_access_token,
    "token_type": "bearer"
  }

@router.post("/register")
async def register(
  # Wir sollten diese Parameter im nächsten Schritt durch ein Pydantic-Schema (UserCreate) ersetzen!
  email: str = Body(...), 
  password: str = Body(...), 
  first_name: str = Body(...), 
  last_name: str = Body(...), 
  db: AsyncSession = Depends(get_db)
):
  existing = await get_user_by_email(db, email)
  if existing:
    raise DomainException("Email already registered", error_code="EMAIL_EXISTS", status_code=400)
  
  user_data = {
    "email": email,
    "hashed_password": get_password_hash(password),
    "first_name": first_name,
    "last_name": last_name
  }
  return await create_user(db, user_data)

@router.post("/forgot-password-request")
async def forgot_password_request(
  email: str, 
  background_tasks: BackgroundTasks,
  db: AsyncSession = Depends(get_db)
):
  user = await get_user_by_email(db, email)
  
  # Always return 200 OK to prevent email enumeration attacks (Security Best Practice)
  if not user:
    return {"message": "If this email exists, an OTP has been sent."}
  
  # 1. Invalidate any existing reset tokens for this user
  await db.execute(delete(PasswordReset).where(PasswordReset.email == email))
  
  # 2. Generate a cryptographically secure 6-digit OTP
  otp_code = ''.join(secrets.choice(string.digits) for _ in range(6))
  
  # 3. Store the HASHED otp in the database (expires in 15 minutes)
  expires = datetime.utcnow() + timedelta(minutes=15)
  reset_record = PasswordReset(
    email=email,
    otp_hash=get_password_hash(otp_code),
    expires_at=expires
  )
  db.add(reset_record)
  await db.commit()
  
  # 4. Schedule the email to be sent in the background (does not block HTTP response)
  background_tasks.add_task(send_otp_email, email, otp_code)
  
  return {"message": "If this email exists, an OTP has been sent."}

@router.post("/reset-password")
async def reset_password(
  email: str, 
  otp: str, 
  new_password: str,
  db: AsyncSession = Depends(get_db)
):
  # 1. Find the latest OTP record for this email
  result = await db.execute(
    select(PasswordReset).where(PasswordReset.email == email)
  )
  reset_record = result.scalar_one_or_none()
  
  # 2. Validate existence, expiration, and hash
  if not reset_record:
    raise DomainException("Invalid or expired OTP", status_code=400)
    
  if reset_record.expires_at < datetime.utcnow():
    await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_record.id))
    await db.commit()
    raise DomainException("OTP has expired", status_code=400)
    
  if not verify_password(otp, reset_record.otp_hash):
    raise DomainException("Invalid OTP", status_code=400)
  
  # 3. Validation passed! Update the user's password
  user = await get_user_by_email(db, email)
  if not user:
    raise DomainException("User not found", status_code=404)
    
  user.hashed_password = get_password_hash(new_password)
  db.add(user)
  
  # 4. Consume (delete) the OTP so it cannot be used again
  await db.execute(delete(PasswordReset).where(PasswordReset.id == reset_record.id))
  await db.commit()
  
  return {"message": "Password updated successfully."}