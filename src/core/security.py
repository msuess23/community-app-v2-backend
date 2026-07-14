from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from pydantic import BaseModel, ValidationError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from src.core.config import settings


# New hashes use Argon2. Existing bcrypt hashes remain readable and are
# transparently upgraded after the next successful login.
_password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


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


def verify_and_update_password(
    plain_password: str,
    hashed_password: str,
) -> tuple[bool, str | None]:
    """
    Verify a password and optionally return a modernized hash.

    Invalid or unknown hashes are treated as a failed login instead of causing
    an HTTP 500 response.
    """
    try:
        return _password_hash.verify_and_update(plain_password, hashed_password)
    except (UnknownHashError, ValueError, TypeError):
        return False, None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    valid, _ = verify_and_update_password(plain_password, hashed_password)
    return valid


def get_password_hash(password: str) -> str:
    return _password_hash.hash(password)


def create_unusable_password_hash() -> str:
    """Create a syntactically valid hash that no user knows the password for."""
    return get_password_hash(secrets.token_urlsafe(48))


def _create_token(
    *,
    subject: str | uuid.UUID,
    token_type: TokenType,
    auth_version: int,
    expires_delta: timedelta,
    token_id: uuid.UUID | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type.value,
        "jti": str(token_id or uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "ver": auth_version,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str | uuid.UUID, *, auth_version: int) -> str:
    return _create_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        auth_version=auth_version,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    subject: str | uuid.UUID,
    *,
    auth_version: int,
    token_id: uuid.UUID | None = None,
) -> str:
    return _create_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        auth_version=auth_version,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_id=token_id,
    )


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
