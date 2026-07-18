from sqlalchemy import JSON

from src.office.models import Office, OfficeHistory
from src.user.models import User, UserHistory


def test_required_orm_columns_match_application_invariants() -> None:
  assert User.__table__.c.role.nullable is False
  assert User.__table__.c.is_active.nullable is False
  assert Office.__table__.c.services.nullable is False
  assert Office.__table__.c.opening_hours.nullable is False
  assert UserHistory.__table__.c.changed_by_user_id.nullable is False
  assert OfficeHistory.__table__.c.changed_by_user_id.nullable is False


def test_office_history_uses_structured_address_snapshot() -> None:
  assert isinstance(OfficeHistory.__table__.c.address_snapshot.type, JSON)
  assert UserHistory.__table__.c.changed_by_user_id.foreign_keys
  assert OfficeHistory.__table__.c.changed_by_user_id.foreign_keys
