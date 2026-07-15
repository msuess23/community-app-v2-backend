from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

import bcrypt
import jwt

from src.core.config import settings
from src.core.exceptions import UnauthorizedException

ACCESS_TOKEN_TYPE = "access"


def normalize_email(email: str) -> str:
  """Returns the canonical representation used for storing and looking up emails."""
  return email.strip().lower()


def ensure_bcrypt_compatible(password: str) -> str:
  """Rejects passwords that bcrypt cannot process without truncation."""
  if len(password.encode("utf-8")) > 72:
    raise ValueError("Password must not exceed 72 UTF-8 bytes")
  return password


def verify_password(plain_password: str, hashed_password: str) -> bool:
  """Verifies a password and safely rejects malformed stored hashes."""
  try:
    return bcrypt.checkpw(
      plain_password.encode("utf-8"),
      hashed_password.encode("utf-8")
    )
  except (TypeError, ValueError):
    return False


def get_password_hash(password: str) -> str:
  """Generates a bcrypt hash for a password."""
  ensure_bcrypt_compatible(password)
  return bcrypt.hashpw(
    password.encode("utf-8"),
    bcrypt.gensalt()
  ).decode("utf-8")


def create_access_token(subject: str | uuid.UUID) -> str:
  """Creates a short-lived JWT used exclusively for API authentication."""
  expire = datetime.now(timezone.utc) + timedelta(
    minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
  )
  payload = {
    "exp": expire,
    "sub": str(subject),
    "type": ACCESS_TOKEN_TYPE,
  }
  return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
  """Decodes a JWT and enforces the expected token type and required claims."""
  try:
    payload = jwt.decode(
      token,
      settings.SECRET_KEY,
      algorithms=[settings.ALGORITHM],
      options={"require": ["exp", "sub", "type"]},
    )
  except jwt.PyJWTError as exc:
    raise UnauthorizedException("Could not validate credentials") from exc

  if payload.get("type") != expected_type:
    raise UnauthorizedException("Invalid token type")

  return payload


def generate_refresh_token() -> str:
  """Creates an opaque refresh token. Only its hash is stored in the database."""
  return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
  """Returns a stable SHA-256 fingerprint for an opaque token."""
  return hashlib.sha256(token.encode("utf-8")).hexdigest()
