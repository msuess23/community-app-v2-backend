import uuid
from datetime import datetime

from src.user.models import User, UserHistory


def build_user_history(
  user: User,
  *,
  actor_id: uuid.UUID,
  change_reason: str,
  valid_from: datetime,
) -> UserHistory:
  """Create an immutable snapshot of the user's current domain state."""
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
    changed_by_user_id=actor_id,
    change_reason=change_reason,
  )
