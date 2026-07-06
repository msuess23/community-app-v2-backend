from datetime import datetime, timedelta, timezone
from typing import Any, Union
import jwt
from passlib.context import CryptContext

from src.core.config import settings

# Setup bcrypt for secure password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
  """Verifies a plain password against the stored hash."""
  return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
  """Generates a bcrypt hash for a new password."""
  return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
  """
  Creates a short-lived JSON Web Token for API authentication.
  The 'subject' (sub) typically holds the user's UUID.
  """
  if expires_delta:
    expire = datetime.now(timezone.utc) + expires_delta
  else:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
  
  to_encode = {
    "exp": expire, 
    "sub": str(subject), 
    "type": "access"
  }
  
  encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
  return encoded_jwt

def create_refresh_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
  """
  Creates a long-lived JWT used to obtain new access tokens.
  """
  if expires_delta:
    expire = datetime.now(timezone.utc) + expires_delta
  else:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
  
  to_encode = {
    "exp": expire, 
    "sub": str(subject), 
    "type": "refresh"
  }
  
  encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
  return encoded_jwt