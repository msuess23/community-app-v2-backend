from datetime import datetime, timedelta, timezone
import jwt
import bcrypt
from src.core.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
  """Verifies a plain password against the stored hash."""
  # encoging strings because bcrypt requires bytes
  password_bytes = plain_password.encode('utf-8')
  hash_bytes = hashed_password.encode('utf-8')
  return bcrypt.checkpw(password_bytes, hash_bytes)

def get_password_hash(password: str) -> str:
  """Generates a bcrypt hash for a new password."""
  password_bytes = password.encode('utf-8')
  salt = bcrypt.gensalt()
  hashed_password = bcrypt.hashpw(password_bytes, salt)
  # decode back to string to store it in the database
  return hashed_password.decode('utf-8')

def create_access_token(subject: str | uuid.UUID) -> str:
  """Creates a short-lived JWT for API authentication."""
  expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
  to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
  return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(subject: str | uuid.UUID) -> str:
  """Creates a long-lived JWT for refreshing access tokens."""
  expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
  to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
  return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)