from collections.abc import Iterable

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.exceptions import AuthenticationException, ForbiddenException
from src.core.security import TokenType, TokenValidationError, decode_token
from src.user.models import Role, User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.BASE_URL}/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        claims = decode_token(token, expected_type=TokenType.ACCESS)
    except TokenValidationError as exc:
        raise AuthenticationException("Could not validate credentials") from exc

    user = await db.get(User, claims.sub)
    if user is None or not user.is_active:
        raise AuthenticationException("Could not validate credentials")

    # Incremented after password changes and account deactivation. This makes
    # already-issued access tokens invalid immediately without a token blacklist.
    if user.auth_version != claims.ver:
        raise AuthenticationException("Session is no longer valid")

    return user


def role_required(allowed_roles: Iterable[Role | str]):
    allowed = {
        role if isinstance(role, Role) else Role(role)
        for role in allowed_roles
    }

    async def guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise ForbiddenException("Insufficient permissions")
        return current_user

    return guard
