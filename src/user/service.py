import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.lifecycle_guard import AppointmentLifecycleGuard
from src.auth.repository import AuthRepository
from src.core.exceptions import (
  ConflictException,
  DomainValidationException,
  ForbiddenException,
  ResourceNotFoundException,
)
from src.core.filters import LifecycleStatusFilter, SortOrder
from src.core.schemas import PaginatedResponse
from src.core.security import get_password_hash
from src.office.repository import OfficeRepository
from src.ticket.services.lifecycle_guard import TicketLifecycleGuard
from src.user.models import Role, User, UserHistory, UserSortField
from src.user.repository import UserRepository
from src.user.roles import CASE_WORKER_ROLES, OFFICE_REQUIRED_ROLES
from src.user.schemas import AdminUserUpdate, UserUpdate


class UserService:
  """Handles business logic for user management."""

  @staticmethod
  def add_history_snapshot(
    db: AsyncSession,
    user: User,
    *,
    changed_by_user_id: uuid.UUID,
    change_reason: str,
  ) -> UserHistory:
    """Stages a snapshot of the currently valid user state."""
    snapshot = UserHistory(
      user_id=user.id,
      email=user.email,
      first_name=user.first_name,
      last_name=user.last_name,
      role=user.role,
      office_id=user.office_id,
      is_active=user.is_active,
      changed_by_user_id=changed_by_user_id,
      change_reason=change_reason,
    )
    UserRepository.add_history(db, snapshot)
    return snapshot

  @staticmethod
  async def _validate_resulting_role_and_office(
    db: AsyncSession,
    user: User,
    update_data: AdminUserUpdate,
    changed_by_user_id: uuid.UUID,
  ) -> tuple[Role, uuid.UUID | None]:
    """Validate the role and office combination produced by an update."""

    resulting_role = update_data.role or user.role

    if user.role != Role.CITIZEN and resulting_role == Role.CITIZEN:
      raise DomainValidationException(
        "A staff account cannot be changed back to a citizen account.",
        error_code="STAFF_TO_CITIZEN_NOT_ALLOWED",
      )

    if (
      user.id == changed_by_user_id
      and user.role == Role.ADMIN
      and resulting_role != Role.ADMIN
    ):
      raise ForbiddenException("Administrators cannot change their own admin role")

    if resulting_role in {Role.CITIZEN, Role.ADMIN}:
      return resulting_role, None

    if "office_id" in update_data.model_fields_set:
      resulting_office_id = update_data.office_id
    else:
      resulting_office_id = user.office_id

    if (
      resulting_role in OFFICE_REQUIRED_ROLES
      and resulting_office_id is None
    ):
      raise DomainValidationException(
        "Officers and managers must be assigned to an active office.",
        error_code="OFFICE_REQUIRED_FOR_ROLE",
      )

    if resulting_office_id is not None:
      office = await OfficeRepository.get_by_id(db, resulting_office_id)
      if office is None:
        raise ResourceNotFoundException(
          "Office not found",
          error_code="OFFICE_NOT_FOUND",
        )
      if not office.is_active:
        raise DomainValidationException(
          "Users cannot be assigned to an inactive office.",
          error_code="OFFICE_INACTIVE",
        )

    return resulting_role, resulting_office_id

  @staticmethod
  async def update_user_profile(
    db: AsyncSession,
    user: User,
    update_data: Union[UserUpdate, AdminUserUpdate],
    changed_by_user_id: uuid.UUID,
  ) -> User:
    """Apply profile changes and store the previous state in history."""

    if not user.is_active:
      raise DomainValidationException(
        "Cannot update a deactivated user profile.",
        error_code="USER_INACTIVE",
      )

    if isinstance(update_data, AdminUserUpdate):
      resulting_role, resulting_office_id = (
        await UserService._validate_resulting_role_and_office(
          db,
          user,
          update_data,
          changed_by_user_id,
        )
      )
      update_dict = update_data.model_dump(
        exclude_unset=True,
        exclude={"change_reason", "role", "office_id"},
      )
      update_dict["role"] = resulting_role
      update_dict["office_id"] = resulting_office_id
      change_reason = update_data.change_reason

      role_or_office_changes = (
        resulting_role != user.role or resulting_office_id != user.office_id
      )
      if role_or_office_changes:
        await TicketLifecycleGuard.ensure_user_is_not_required(
          db,
          user.id,
          operation="reassigned",
        )
        if user.role == Role.CITIZEN and resulting_role != Role.CITIZEN:
          await AppointmentLifecycleGuard.ensure_user_has_no_scheduled_appointments(
            db,
            user.id,
          )
    else:
      update_dict = update_data.model_dump(exclude_unset=True)
      change_reason = "Profile updated by user"

    effective_changes = {
      key: value
      for key, value in update_dict.items()
      if getattr(user, key) != value
    }
    if not effective_changes:
      return user

    for key, value in effective_changes.items():
      setattr(user, key, value)

    UserRepository.add(db, user)
    await db.flush()
    UserService.add_history_snapshot(
      db,
      user,
      changed_by_user_id=changed_by_user_id,
      change_reason=change_reason,
    )
    await db.flush()
    await db.refresh(user)
    return user

  @staticmethod
  async def get_all_users(
    db: AsyncSession,
    current_user: User,
    *,
    page: int = 1,
    size: int = 20,
    office_id: Optional[uuid.UUID] = None,
    role: Optional[Role] = None,
    status: LifecycleStatusFilter = LifecycleStatusFilter.ACTIVE,
    search: Optional[str] = None,
    sort_by: UserSortField = UserSortField.LAST_NAME,
    order: SortOrder = SortOrder.ASC,
  ) -> PaginatedResponse:
    """Return users visible within the caller role and office scope."""

    if current_user.role != Role.ADMIN and status != LifecycleStatusFilter.ACTIVE:
      raise DomainValidationException(
        "Only administrators may filter inactive users.",
        error_code="LIFECYCLE_FILTER_NOT_ALLOWED",
      )
    if current_user.role != Role.ADMIN and role == Role.CITIZEN:
      raise DomainValidationException(
        "Only administrators may search citizen accounts.",
        error_code="ROLE_FILTER_NOT_ALLOWED",
      )
    if (
      current_user.role in CASE_WORKER_ROLES
      and office_id is not None
      and office_id != current_user.office_id
    ):
      raise DomainValidationException(
        "The office filter is outside the caller's scope.",
        error_code="OFFICE_FILTER_OUTSIDE_SCOPE",
      )

    exclude_citizens = current_user.role != Role.ADMIN
    force_office_id = (
      current_user.office_id
      if current_user.role in CASE_WORKER_ROLES
      else None
    )
    effective_status = (
      status if current_user.role == Role.ADMIN else LifecycleStatusFilter.ACTIVE
    )

    users, total = await UserRepository.get_page(
      db,
      page=page,
      size=size,
      office_id=office_id,
      role=role,
      exclude_citizens=exclude_citizens,
      force_office_id=force_office_id,
      status=effective_status,
      search=search,
      sort_by=sort_by,
      order=order,
    )
    return PaginatedResponse.create(data=users, total=total, page=page, size=size)

  @staticmethod
  async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Load one user account or raise the canonical not-found error."""

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
    admin_id: uuid.UUID,
    change_reason: str,
  ) -> None:
    """Deactivate an account and append its final active-state snapshot."""

    user = await UserService.get_user_by_id(db, user_id)

    if user.id == admin_id:
      raise ForbiddenException("Administrators cannot deactivate their own account")

    if not user.is_active:
      raise ConflictException(
        "User is already deactivated",
        error_code="USER_ALREADY_DEACTIVATED",
      )

    await TicketLifecycleGuard.ensure_user_is_not_required(
      db,
      user.id,
      operation="deactivated",
    )
    if user.role == Role.CITIZEN:
      await AppointmentLifecycleGuard.ensure_user_has_no_scheduled_appointments(
        db,
        user.id,
      )

    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.hashed_password = get_password_hash(secrets.token_urlsafe(32))

    if user.role == Role.CITIZEN:
      user.email = f"deleted+{user.id}@users.invalid"
      user.first_name = "gelöschter"
      user.last_name = "Nutzer"

    UserRepository.add(db, user)
    await AuthRepository.delete_refresh_tokens_by_user_id(db, user.id)
    await db.flush()
    UserService.add_history_snapshot(
      db,
      user,
      changed_by_user_id=admin_id,
      change_reason=change_reason,
    )
    await db.flush()

  @staticmethod
  async def run_deep_anonymization(
    db: AsyncSession,
    *,
    retention_days: int = 180,
  ) -> None:
    """Anonymizes only old history snapshots belonging to deleted citizens."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    await UserRepository.bulk_anonymize_citizen_history(db, cutoff)

  @staticmethod
  async def get_user_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    size: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
  ) -> PaginatedResponse:
    """Return a paginated append-only history for one user."""

    await UserService.get_user_by_id(db, user_id)
    history, total = await UserRepository.get_history_page(
      db,
      user_id,
      page=page,
      size=size,
      start_date=start_date,
      end_date=end_date,
    )
    return PaginatedResponse.create(
      data=history,
      total=total,
      page=page,
      size=size,
    )
