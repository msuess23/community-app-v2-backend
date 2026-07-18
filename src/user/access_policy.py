"""Object-level authorization rules for user resources."""

from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


class UserAccessPolicy:
  """Centralize profile visibility independently from authentication."""

  @staticmethod
  def can_access(current_user: User, target_user: User) -> bool:
    """Return whether the caller may read the target user profile."""

    if current_user.id == target_user.id:
      return True
    if current_user.role == Role.ADMIN:
      return True
    if not target_user.is_active or target_user.role == Role.CITIZEN:
      return False
    if current_user.role == Role.DISPATCHER:
      return True
    if current_user.role in CASE_WORKER_ROLES:
      return (
        current_user.office_id is not None
        and current_user.office_id == target_user.office_id
      )
    return False
