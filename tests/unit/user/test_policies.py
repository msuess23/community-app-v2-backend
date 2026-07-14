import uuid

import pytest

from src.core.exceptions import ForbiddenException
from src.core.filters import LifecycleStatusFilter
from src.user.models import Role, User
from src.user.policies import UserPolicy


def make_user(
  role: Role,
  *,
  office_id: uuid.UUID | None = None,
  is_active: bool = True,
) -> User:
  user_id = uuid.uuid4()
  return User(
    id=user_id,
    email=f"{user_id}@example.test",
    hashed_password="not-used-by-policy-tests",
    first_name="Test",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=is_active,
  )


def test_user_can_always_read_own_profile() -> None:
  citizen = make_user(Role.CITIZEN)
  assert UserPolicy.can_read(citizen, citizen)


def test_citizen_cannot_read_another_profile() -> None:
  actor = make_user(Role.CITIZEN)
  target = make_user(Role.CITIZEN)
  assert not UserPolicy.can_read(actor, target)


def test_admin_can_read_inactive_citizen() -> None:
  actor = make_user(Role.ADMIN)
  target = make_user(Role.CITIZEN, is_active=False)
  assert UserPolicy.can_read(actor, target)


def test_dispatcher_can_read_active_staff_but_not_citizens_or_inactive_users() -> None:
  actor = make_user(Role.DISPATCHER, office_id=uuid.uuid4())

  assert UserPolicy.can_read(actor, make_user(Role.OFFICER, office_id=uuid.uuid4()))
  assert not UserPolicy.can_read(actor, make_user(Role.CITIZEN))
  assert not UserPolicy.can_read(
    actor,
    make_user(Role.OFFICER, office_id=uuid.uuid4(), is_active=False),
  )


@pytest.mark.parametrize("role", [Role.OFFICER, Role.MANAGER])
def test_office_scoped_staff_can_only_read_active_staff_in_own_office(role: Role) -> None:
  own_office = uuid.uuid4()
  actor = make_user(role, office_id=own_office)

  assert UserPolicy.can_read(actor, make_user(Role.OFFICER, office_id=own_office))
  assert not UserPolicy.can_read(actor, make_user(Role.OFFICER, office_id=uuid.uuid4()))
  assert not UserPolicy.can_read(actor, make_user(Role.CITIZEN, office_id=own_office))


def test_list_scope_rejects_cross_office_filter() -> None:
  actor = make_user(Role.OFFICER, office_id=uuid.uuid4())

  with pytest.raises(ForbiddenException):
    UserPolicy.resolve_read_scope(
      actor,
      requested_office_id=uuid.uuid4(),
      requested_role=None,
      requested_status=LifecycleStatusFilter.ACTIVE,
    )


def test_non_admin_list_scope_rejects_inactive_and_citizen_filters() -> None:
  actor = make_user(Role.DISPATCHER)

  with pytest.raises(ForbiddenException):
    UserPolicy.resolve_read_scope(
      actor,
      requested_office_id=None,
      requested_role=None,
      requested_status=LifecycleStatusFilter.INACTIVE,
    )

  with pytest.raises(ForbiddenException):
    UserPolicy.resolve_read_scope(
      actor,
      requested_office_id=None,
      requested_role=Role.CITIZEN,
      requested_status=LifecycleStatusFilter.ACTIVE,
    )


def test_admin_scope_preserves_requested_filters() -> None:
  office_id = uuid.uuid4()
  actor = make_user(Role.ADMIN)

  scope = UserPolicy.resolve_read_scope(
    actor,
    requested_office_id=office_id,
    requested_role=Role.CITIZEN,
    requested_status=LifecycleStatusFilter.INACTIVE,
  )

  assert scope.office_id == office_id
  assert scope.role == Role.CITIZEN
  assert scope.status == LifecycleStatusFilter.INACTIVE
  assert not scope.exclude_citizens


def test_admin_cannot_remove_own_role_or_deactivate_self() -> None:
  actor = make_user(Role.ADMIN)

  with pytest.raises(ForbiddenException):
    UserPolicy.require_can_admin_update(
      actor,
      actor,
      new_role=Role.OFFICER,
    )

  with pytest.raises(ForbiddenException):
    UserPolicy.require_can_deactivate(actor, actor)
