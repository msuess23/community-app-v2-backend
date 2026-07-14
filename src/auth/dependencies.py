import uuid
from collections.abc import Iterable

from fastapi import Depends, Path
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.exceptions import AuthenticationException, ForbiddenException
from src.core.security import TokenType, TokenValidationError, decode_token
from src.auth.repository import AuthRepository
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

    # Temporary compatibility until the raw blacklist is replaced by refresh
    # sessions in step 2. Keeping this check preserves current logout behavior.
    if await AuthRepository.is_token_blacklisted(db, token):
        raise AuthenticationException("Token has been revoked")

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


async def get_target_user_if_allowed(
    user_id: uuid.UUID = Path(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    if current_user.id == user_id:
        return current_user

    if current_user.role is Role.CITIZEN:
        raise ForbiddenException("You do not have permission to access this resource.")

    # The detailed office/role policy is handled in the separate S-2 refactor.
    from src.user.service import UserService

    return await UserService.get_user_by_id(db, user_id)
