import uuid
from dataclasses import dataclass

from src.core.exceptions import ForbiddenException
from src.core.filters import LifecycleStatusFilter
from src.user.models import Role, User


@dataclass(frozen=True, slots=True)
class UserReadScope:
  """Effective database scope for a user-list request."""

  office_id: uuid.UUID | None
  role: Role | None
  status: LifecycleStatusFilter
  exclude_citizens: bool

  def contains(self, target: User) -> bool:
    """Return whether a concrete user belongs to this read scope."""
    if self.status == LifecycleStatusFilter.ACTIVE and not target.is_active:
      return False
    if self.status == LifecycleStatusFilter.INACTIVE and target.is_active:
      return False
    if self.exclude_citizens and target.role == Role.CITIZEN:
      return False
    if self.office_id is not None and target.office_id != self.office_id:
      return False
    if self.role is not None and target.role != self.role:
      return False
    return True


class UserPolicy:
  """Central object- and collection-level authorization for user resources."""

  _OFFICE_SCOPED_ROLES = frozenset({Role.OFFICER, Role.MANAGER})

  @classmethod
  def resolve_read_scope(
    cls,
    actor: User,
    *,
    requested_office_id: uuid.UUID | None,
    requested_role: Role | None,
    requested_status: LifecycleStatusFilter,
  ) -> UserReadScope:
    """
    Resolve client filters into the maximum scope the actor may access.

    Rejecting forbidden filters explicitly prevents callers from probing a
    broader namespace and keeps list and detail authorization equivalent.
    """
    if actor.role == Role.ADMIN:
      return UserReadScope(
        office_id=requested_office_id,
        role=requested_role,
        status=requested_status,
        exclude_citizens=False,
      )

    if actor.role == Role.CITIZEN:
      raise ForbiddenException("Citizens cannot list user accounts.")

    if requested_status != LifecycleStatusFilter.ACTIVE:
      raise ForbiddenException("Only administrators may access inactive users.")

    if requested_role == Role.CITIZEN:
      raise ForbiddenException("Only administrators may access citizen accounts.")

    effective_office_id = requested_office_id
    if actor.role in cls._OFFICE_SCOPED_ROLES:
      if actor.office_id is None:
        raise ForbiddenException(
          "Your account is not assigned to an office and cannot access staff accounts."
        )
      if requested_office_id is not None and requested_office_id != actor.office_id:
        raise ForbiddenException("You may only access users from your own office.")
      effective_office_id = actor.office_id
    elif actor.role != Role.DISPATCHER:
      raise ForbiddenException("You do not have permission to access user accounts.")

    return UserReadScope(
      office_id=effective_office_id,
      role=requested_role,
      status=LifecycleStatusFilter.ACTIVE,
      exclude_citizens=True,
    )

  @classmethod
  def can_read(cls, actor: User, target: User) -> bool:
    """Apply the same scope rules used by the collection endpoint."""
    if actor.id == target.id or actor.role == Role.ADMIN:
      return True

    try:
      scope = cls.resolve_read_scope(
        actor,
        requested_office_id=None,
        requested_role=None,
        requested_status=LifecycleStatusFilter.ACTIVE,
      )
    except ForbiddenException:
      return False

    return scope.contains(target)

  @classmethod
  def require_can_read(cls, actor: User, target: User) -> None:
    if not cls.can_read(actor, target):
      raise ForbiddenException("You do not have permission to access this user.")

  @staticmethod
  def require_can_admin_update(
    actor: User,
    target: User,
    *,
    new_role: Role | None,
  ) -> None:
    """Protect administrative updates, including self-lockout scenarios."""
    if actor.role != Role.ADMIN:
      raise ForbiddenException("Only administrators may update other users.")

    if actor.id == target.id and new_role is not None and new_role != Role.ADMIN:
      raise ForbiddenException("Administrators cannot remove their own administrator role.")

  @staticmethod
  def require_can_deactivate(actor: User, target: User) -> None:
    """Prevent accidental loss of the currently authenticated admin account."""
    if actor.role != Role.ADMIN:
      raise ForbiddenException("Only administrators may deactivate users.")
    if actor.id == target.id:
      raise ForbiddenException("Administrators cannot deactivate their own account.")
