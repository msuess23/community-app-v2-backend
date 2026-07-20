"""Object-level authorization rules for mutable Info resources."""

from __future__ import annotations

import uuid

from src.core.exceptions import ForbiddenException
from src.info.models import Info
from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


class InfoAccessPolicy:
  """Enforce Info ownership rules without database or service dependencies."""

  @staticmethod
  def require_manage_permission(info: Info, current_user: User) -> None:
    """Allow administrators or case workers assigned to the owning office."""

    if current_user.role == Role.ADMIN:
      return
    if (
      current_user.role not in CASE_WORKER_ROLES
      or info.office_id is None
      or current_user.office_id != info.office_id
    ):
      raise ForbiddenException()

  @staticmethod
  def require_create_permission(
    office_id: uuid.UUID | None,
    current_user: User,
  ) -> None:
    """Restrict case workers to creating Infos for their own office."""

    if current_user.role == Role.ADMIN:
      return
    if (
      current_user.role not in CASE_WORKER_ROLES
      or office_id is None
      or office_id != current_user.office_id
    ):
      raise ForbiddenException(
        "Case workers may create Infos only for their own office."
      )

  @staticmethod
  def require_reassignment_permission(
    info: Info,
    new_office_id: uuid.UUID | None,
    current_user: User,
  ) -> None:
    """Allow only administrators to move an Info to another office."""

    if current_user.role != Role.ADMIN and new_office_id != info.office_id:
      raise ForbiddenException("Only administrators may reassign an Info.")
