from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class IssuedToken:
    value: str
    jti: uuid.UUID
    expires_at: datetime


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


def hash_token(token: str) -> str:
    """Return a deterministic, non-reversible fingerprint for token storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_hash_matches(token: str, expected_hash: str) -> bool:
    """Compare a presented token with its stored fingerprint in constant time."""
    return hmac.compare_digest(hash_token(token), expected_hash)


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


def issue_refresh_token(
    subject: str | uuid.UUID,
    *,
    auth_version: int,
    token_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> IssuedToken:
    issued_at = datetime.now(timezone.utc)
    effective_expires_at = expires_at or (
        issued_at + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    jti = token_id or uuid.uuid4()
    value = _create_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        auth_version=auth_version,
        issued_at=issued_at,
        expires_at=effective_expires_at,
        token_id=jti,
    )
    return IssuedToken(
        value=value,
        jti=jti,
        expires_at=effective_expires_at,
    )


def create_refresh_token(
    subject: str | uuid.UUID,
    *,
    auth_version: int,
    token_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Compatibility wrapper for code that only needs the encoded token."""
    return issue_refresh_token(
        subject,
        auth_version=auth_version,
        token_id=token_id,
        expires_at=expires_at,
    ).value


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
