import uuid
from dataclasses import dataclass

from src.core.exceptions import DomainValidationException, ForbiddenException
from src.core.filters import LifecycleStatusFilter
from src.user.models import Role, User


@dataclass(frozen=True, slots=True)
class UserListScope:
  """Effective filters for an authorized user-list request."""

  office_id: uuid.UUID | None
  role: Role | None
  status: LifecycleStatusFilter
  exclude_citizens: bool = False


class UserPolicy:
  """Small collection of user assignment and authorization rules."""

  OFFICE_ROLES = frozenset({Role.DISPATCHER, Role.OFFICER, Role.MANAGER})

  @classmethod
  def validate_assignment(
    cls,
    *,
    role: Role,
    office_id: uuid.UUID | None,
  ) -> None:
    if role in cls.OFFICE_ROLES and office_id is None:
      raise DomainValidationException(
        "Staff accounts must be assigned to an office.",
        error_code="USER_OFFICE_REQUIRED",
        details={"field": "office_id", "role": role.value},
      )
    if role not in cls.OFFICE_ROLES and office_id is not None:
      raise DomainValidationException(
        "Citizen and administrator accounts cannot be assigned to an office.",
        error_code="USER_OFFICE_NOT_ALLOWED",
        details={"field": "office_id", "role": role.value},
      )

  @classmethod
  def requires_office(cls, role: Role) -> bool:
    return role in cls.OFFICE_ROLES

  @classmethod
  def list_scope(
    cls,
    actor: User,
    *,
    office_id: uuid.UUID | None,
    role: Role | None,
    status: LifecycleStatusFilter,
  ) -> UserListScope:
    if actor.role == Role.ADMIN:
      return UserListScope(office_id, role, status)

    if actor.role == Role.CITIZEN:
      raise ForbiddenException("Citizens cannot list user accounts.")
    if status != LifecycleStatusFilter.ACTIVE:
      raise ForbiddenException("Only administrators may access inactive users.")
    if role == Role.CITIZEN:
      raise ForbiddenException("Only administrators may access citizen accounts.")

    if actor.role in {Role.OFFICER, Role.MANAGER}:
      if actor.office_id is None:
        raise ForbiddenException("Your account is not assigned to an office.")
      if office_id is not None and office_id != actor.office_id:
        raise ForbiddenException("You may only access users from your own office.")
      office_id = actor.office_id
    elif actor.role != Role.DISPATCHER:
      raise ForbiddenException()

    return UserListScope(
      office_id=office_id,
      role=role,
      status=LifecycleStatusFilter.ACTIVE,
      exclude_citizens=True,
    )

  @staticmethod
  def can_read(actor: User, target: User) -> bool:
    if actor.id == target.id or actor.role == Role.ADMIN:
      return True
    if not target.is_active or target.role == Role.CITIZEN:
      return False
    if actor.role == Role.DISPATCHER:
      return True
    return (
      actor.role in {Role.OFFICER, Role.MANAGER}
      and actor.office_id is not None
      and actor.office_id == target.office_id
    )

  @classmethod
  def require_can_read(cls, actor: User, target: User) -> None:
    if not cls.can_read(actor, target):
      raise ForbiddenException("You do not have permission to access this user.")

  @staticmethod
  def require_admin_update(
    actor: User,
    target: User,
    *,
    new_role: Role | None,
  ) -> None:
    if actor.role != Role.ADMIN:
      raise ForbiddenException("Only administrators may update other users.")
    if actor.id == target.id and new_role not in {None, Role.ADMIN}:
      raise ForbiddenException("Administrators cannot remove their own administrator role.")

  @staticmethod
  def require_deactivation(actor: User, target: User) -> None:
    if actor.role != Role.ADMIN:
      raise ForbiddenException("Only administrators may deactivate users.")
    if actor.id == target.id:
      raise ForbiddenException("Administrators cannot deactivate their own account.")
