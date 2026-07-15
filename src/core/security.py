from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from pydantic import BaseModel, ValidationError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

from src.core.config import settings


# The study project starts with a fresh database, so Argon2 is sufficient.
_password_hash = PasswordHash((Argon2Hasher(),))


class TokenType(str, Enum):
    ACCESS = "access"


class TokenClaims(BaseModel):
    sub: uuid.UUID
    type: TokenType
    jti: uuid.UUID
    iat: datetime
    exp: datetime
    iss: str
    aud: str
    ver: int


class TokenValidationError(Exception):
    """Raised when a JWT is invalid or has the wrong semantic type."""


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Treat unknown or malformed hashes as an ordinary failed login."""
    try:
        return _password_hash.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    return _password_hash.hash(password)


def create_unusable_password_hash() -> str:
    """Create a syntactically valid hash that no user knows the password for."""
    return get_password_hash(secrets.token_urlsafe(48))


def hash_token(token: str) -> str:
    """Return a deterministic, non-reversible fingerprint for token storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_token(
    *,
    subject: str | uuid.UUID,
    token_type: TokenType,
    auth_version: int,
    issued_at: datetime,
    expires_at: datetime,
    token_id: uuid.UUID,
) -> str:
    payload = {
        "sub": str(subject),
        "type": token_type.value,
        "jti": str(token_id),
        "iat": issued_at,
        "exp": expires_at,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "ver": auth_version,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | uuid.UUID, *, auth_version: int) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return _create_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        auth_version=auth_version,
        issued_at=issued_at,
        expires_at=expires_at,
        token_id=uuid.uuid4(),
    )


def create_refresh_token() -> str:
    """Create an opaque refresh token that is stored only as a SHA-256 hash."""
    return secrets.token_urlsafe(48)


def decode_token(token: str, *, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            leeway=settings.JWT_LEEWAY_SECONDS,
            options={
                "require": [
                    "sub",
                    "type",
                    "jti",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                    "ver",
                ]
            },
        )
        claims = TokenClaims.model_validate(payload)
    except (jwt.exceptions.InvalidTokenError, ValidationError, ValueError, TypeError) as exc:
        raise TokenValidationError("Invalid token") from exc

    if claims.type is not expected_type:
        raise TokenValidationError("Unexpected token type")

    return claims
