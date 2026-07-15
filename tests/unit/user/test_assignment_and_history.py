import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.core.exceptions import DomainValidationException
from src.user.audit import build_user_history
from src.user.models import Role, User
from src.user.policies import UserPolicy
from src.user.schemas import AdminUserCreate, UserCreate, UserUpdate


@pytest.mark.parametrize("role", [Role.DISPATCHER, Role.OFFICER, Role.MANAGER])
def test_staff_roles_require_an_office(role: Role) -> None:
  with pytest.raises(DomainValidationException) as raised:
    UserPolicy.validate_assignment(role=role, office_id=None)
  assert raised.value.error_code == "USER_OFFICE_REQUIRED"


@pytest.mark.parametrize("role", [Role.CITIZEN, Role.ADMIN])
def test_citizens_and_admins_reject_office_assignments(role: Role) -> None:
  with pytest.raises(DomainValidationException) as raised:
    UserPolicy.validate_assignment(role=role, office_id=uuid.uuid4())
  assert raised.value.error_code == "USER_OFFICE_NOT_ALLOWED"


def test_valid_assignments_are_accepted() -> None:
  UserPolicy.validate_assignment(role=Role.CITIZEN, office_id=None)
  UserPolicy.validate_assignment(role=Role.ADMIN, office_id=None)
  UserPolicy.validate_assignment(
    role=Role.OFFICER,
    office_id=uuid.uuid4(),
  )


def test_email_payloads_are_normalized_before_persistence() -> None:
  citizen = UserCreate(
    email="  Mixed.Case@Example.COM ",
    password="correct horse battery staple",
    first_name="Test",
    last_name="Citizen",
  )
  staff = AdminUserCreate(
    email=" Staff@Example.COM ",
    password="correct horse battery staple",
    first_name="Test",
    last_name="Officer",
    role=Role.OFFICER,
    office_id=uuid.uuid4(),
  )

  assert str(citizen.email) == "mixed.case@example.com"
  assert str(staff.email) == "staff@example.com"


def test_change_reason_is_required_for_user_updates() -> None:
  with pytest.raises(ValidationError):
    UserUpdate(first_name="Changed")


def test_user_history_snapshot_contains_assignment_and_lifecycle() -> None:
  now = datetime.now(timezone.utc)
  version_start = now.replace(microsecond=0)
  office_id = uuid.uuid4()
  actor_id = uuid.uuid4()
  user = User(
    id=uuid.uuid4(),
    email="user@example.test",
    hashed_password="unused",
    first_name="Test",
    last_name="User",
    role=Role.OFFICER,
    office_id=office_id,
    is_active=False,
    deactivated_at=now,
    created_at=version_start,
    updated_at=version_start,
  )

  snapshot = build_user_history(
    user,
    actor_id=actor_id,
    change_reason="Account deactivated",
    valid_to=now,
  )

  assert snapshot.office_id == office_id
  assert snapshot.is_active is False
  assert snapshot.deactivated_at == now
  assert snapshot.changed_by_user_id == actor_id
  assert snapshot.valid_from == version_start
  assert snapshot.valid_to == now
