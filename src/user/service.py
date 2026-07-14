import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import RefreshSessionRevokeReason
from src.auth.repository import AuthRepository
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ResourceNotFoundException,
)
from src.core.filters import LifecycleStatusFilter
from src.core.normalization import normalize_email
from src.core.pagination import Page, PaginationParams, SortOrder
from src.core.security import create_unusable_password_hash, get_password_hash
from src.office.repository import OfficeRepository
from src.user.audit import build_user_history
from src.user.models import Role, User, UserHistory
from src.user.persistence import UserPersistence
from src.user.policies import UserAssignmentPolicy, UserPolicy
from src.user.query_repository import UserQueryRepository
from src.user.repository import UserRepository
from src.user.schemas import (
  AdminUserCreate,
  AdminUserUpdate,
  UserResponse,
  UserSortField,
  UserUpdate,
)


logger = logging.getLogger(__name__)


class UserService:
  """Business logic for users, assignments, and temporal audit versions."""

  @staticmethod
  async def _get_locked_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await UserPersistence.get_by_id_for_update(db, user_id)
    if user is None:
      raise ResourceNotFoundException(
        "User not found",
        error_code="USER_NOT_FOUND",
      )
    return user

  @staticmethod
  async def _validate_assignment(
    db: AsyncSession,
    *,
    role: Role,
    office_id: uuid.UUID | None,
  ) -> None:
    UserAssignmentPolicy.validate_shape(role=role, office_id=office_id)
    if not UserAssignmentPolicy.requires_office(role):
      return

    office = await OfficeRepository.get_by_id(db, office_id)
    if office is None:
      raise DomainValidationException(
        "The selected office does not exist.",
        error_code="USER_OFFICE_NOT_FOUND",
        details={"field": "office_id"},
      )
    if not office.is_active:
      raise DomainValidationException(
        "Staff accounts cannot be assigned to an inactive office.",
        error_code="USER_OFFICE_INACTIVE",
        details={"field": "office_id"},
      )

  @staticmethod
  async def create_user_by_admin(
    db: AsyncSession,
    *,
    actor: User,
    user_data: AdminUserCreate,
  ) -> User:
    email = normalize_email(user_data.email)
    if await UserRepository.get_by_email(db, email):
      raise ConflictException(
        "Email already registered",
        error_code="EMAIL_ALREADY_REGISTERED",
      )

    await UserService._validate_assignment(
      db,
      role=user_data.role,
      office_id=user_data.office_id,
    )

    now = datetime.now(timezone.utc)
    new_user = User(
      email=email,
      hashed_password=get_password_hash(user_data.password),
      first_name=user_data.first_name,
      last_name=user_data.last_name,
      role=user_data.role,
      office_id=user_data.office_id,
      created_at=now,
    )
    UserRepository.add(db, new_user)
    await db.flush()
    UserRepository.add_history(
      db,
      build_user_history(
        new_user,
        actor_id=actor.id,
        change_reason=user_data.change_reason,
        valid_from=now,
      ),
    )
    await db.flush()
    return new_user

  @staticmethod
  async def update_user_profile(
    db: AsyncSession,
    user: User,
    update_data: UserUpdate,
    changed_by_user_id: uuid.UUID,
  ) -> User:
    locked_user = await UserService._get_locked_user(db, user.id)
    if not locked_user.is_active:
      raise ConflictException(
        "Cannot update a deactivated user profile.",
        error_code="USER_DEACTIVATED",
      )

    changes = update_data.model_dump(
      exclude_unset=True,
      exclude={"change_reason"},
    )
    if not changes:
      return locked_user

    now = datetime.now(timezone.utc)
    await UserPersistence.close_current_history(
      db,
      locked_user.id,
      valid_to=now,
    )
    for key, value in changes.items():
      setattr(locked_user, key, value)

    UserRepository.add_history(
      db,
      build_user_history(
        locked_user,
        actor_id=changed_by_user_id,
        change_reason=update_data.change_reason,
        valid_from=now,
      ),
    )
    await db.flush()
    return locked_user

  @staticmethod
  async def update_user_by_admin(
    db: AsyncSession,
    *,
    actor: User,
    target_user: User,
    update_data: AdminUserUpdate,
  ) -> User:
    UserPolicy.require_can_admin_update(
      actor,
      target_user,
      new_role=update_data.role,
    )

    locked_user = await UserService._get_locked_user(db, target_user.id)
    if not locked_user.is_active:
      raise ConflictException(
        "Cannot update a deactivated user profile.",
        error_code="USER_DEACTIVATED",
      )

    changes = update_data.model_dump(
      exclude_unset=True,
      exclude={"change_reason"},
    )
    if not changes:
      return locked_user

    resulting_role = changes.get("role", locked_user.role)
    resulting_office_id = changes.get("office_id", locked_user.office_id)
    await UserService._validate_assignment(
      db,
      role=resulting_role,
      office_id=resulting_office_id,
    )

    now = datetime.now(timezone.utc)
    await UserPersistence.close_current_history(
      db,
      locked_user.id,
      valid_to=now,
    )
    for key, value in changes.items():
      setattr(locked_user, key, value)

    UserRepository.add_history(
      db,
      build_user_history(
        locked_user,
        actor_id=actor.id,
        change_reason=update_data.change_reason,
        valid_from=now,
      ),
    )
    await db.flush()
    return locked_user

  @staticmethod
  async def get_all_users(
    db: AsyncSession,
    current_user: User,
    *,
    pagination: PaginationParams,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    sort_by: UserSortField = UserSortField.LAST_NAME,
    order: SortOrder = SortOrder.ASC,
  ) -> Page[UserResponse]:
    scope = UserPolicy.resolve_read_scope(
      current_user,
      requested_office_id=office_id,
      requested_role=role,
      requested_status=status,
    )
    users, total = await UserQueryRepository.get_page(
      db,
      scope=scope,
      pagination=pagination,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    return Page.create(data=users, total=total, pagination=pagination)

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await UserRepository.get_by_id(db, user_id)
    if user is None:
      raise ResourceNotFoundException(
        "User not found",
        error_code="USER_NOT_FOUND",
      )
    return user

  @staticmethod
  async def deactivate_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    actor: User,
    *,
    change_reason: str,
  ) -> None:
    user = await UserService._get_locked_user(db, user_id)
    UserPolicy.require_can_deactivate(actor, user)

    if not user.is_active:
      raise ConflictException(
        "User is already deactivated",
        error_code="USER_ALREADY_DEACTIVATED",
      )

    # Close the still-identifiable version before anonymizing the live row.
    # This preserves the exact pre-deactivation state in the audit timeline.
    now = datetime.now(timezone.utc)
    await UserPersistence.close_current_history(db, user.id, valid_to=now)

    user.is_active = False
    user.deactivated_at = now
    user.email = f"deleted+{user.id}@users.example.com"
    user.first_name = "gelöschter"
    user.last_name = "Nutzer"
    user.hashed_password = create_unusable_password_hash()
    user.auth_version += 1

    UserRepository.add_history(
      db,
      build_user_history(
        user,
        actor_id=actor.id,
        change_reason=change_reason,
        valid_from=now,
      ),
    )
    await AuthRepository.revoke_all_refresh_sessions_for_user(
      db,
      user.id,
      RefreshSessionRevokeReason.ACCOUNT_DEACTIVATED,
      revoked_at=now,
    )
    await db.flush()

  @staticmethod
  async def run_deep_anonymization(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    cutoff_citizen = now - timedelta(days=180)
    cutoff_officer = now - timedelta(days=3650)

    citizen_rows = await UserPersistence.bulk_anonymize_history(
      db,
      [Role.CITIZEN],
      cutoff_citizen,
    )
    staff_rows = await UserPersistence.bulk_anonymize_history(
      db,
      [Role.DISPATCHER, Role.OFFICER, Role.MANAGER, Role.ADMIN],
      cutoff_officer,
    )
    logger.info(
      "Deep anonymization completed",
      extra={
        "completed_at": now.isoformat(),
        "citizen_history_rows": citizen_rows,
        "staff_history_rows": staff_rows,
      },
    )

  @staticmethod
  async def get_user_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> list[UserHistory]:
    await UserService.get_user_by_id(db, user_id)
    return await UserPersistence.get_history_by_user_id(
      db,
      user_id,
      start_date,
      end_date,
    )
