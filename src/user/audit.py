import uuid
from datetime import datetime

from src.user.models import User, UserHistory


def build_user_history(
  user: User,
  *,
  actor_id: uuid.UUID,
  change_reason: str,
  valid_to: datetime,
) -> UserHistory:
  """Archive the user state that was valid immediately before a change."""
  valid_from = user.updated_at or user.created_at or valid_to
  return UserHistory(
    user_id=user.id,
    email=user.email,
    first_name=user.first_name,
    last_name=user.last_name,
    role=user.role,
    office_id=user.office_id,
    is_active=user.is_active,
    deactivated_at=user.deactivated_at,
    valid_from=valid_from,
    valid_to=valid_to,
    changed_by_user_id=actor_id,
    change_reason=change_reason,
  )
