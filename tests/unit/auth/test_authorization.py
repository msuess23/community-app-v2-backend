import uuid

from src.user.access_policy import UserAccessPolicy
from src.user.models import Role, User


def make_user(
  role: Role,
  *,
  office_id: uuid.UUID | None = None,
  active: bool = True,
) -> User:
  return User(
    id=uuid.uuid4(),
    email=f"{uuid.uuid4()}@example.com",
    hashed_password="not-used",
    first_name="Test",
    last_name="User",
    role=role,
    office_id=office_id,
    is_active=active,
  )


def test_citizen_can_only_access_self():
  citizen = make_user(Role.CITIZEN)
  other = make_user(Role.CITIZEN)

  assert UserAccessPolicy.can_access(citizen, citizen) is True
  assert UserAccessPolicy.can_access(citizen, other) is False


def test_officer_and_manager_are_limited_to_active_staff_in_own_office():
  office_id = uuid.uuid4()
  other_office_id = uuid.uuid4()
  officer = make_user(Role.OFFICER, office_id=office_id)
  manager = make_user(Role.MANAGER, office_id=office_id)
  colleague = make_user(Role.OFFICER, office_id=office_id)
  foreign_colleague = make_user(Role.OFFICER, office_id=other_office_id)
  citizen = make_user(Role.CITIZEN, office_id=office_id)
  inactive_colleague = make_user(Role.OFFICER, office_id=office_id, active=False)

  assert UserAccessPolicy.can_access(officer, colleague) is True
  assert UserAccessPolicy.can_access(manager, colleague) is True
  assert UserAccessPolicy.can_access(officer, foreign_colleague) is False
  assert UserAccessPolicy.can_access(officer, citizen) is False
  assert UserAccessPolicy.can_access(officer, inactive_colleague) is False


def test_dispatcher_sees_active_staff_but_not_citizens():
  dispatcher = make_user(Role.DISPATCHER, office_id=uuid.uuid4())

  assert UserAccessPolicy.can_access(dispatcher, make_user(Role.OFFICER)) is True
  assert UserAccessPolicy.can_access(dispatcher, make_user(Role.CITIZEN)) is False
  assert UserAccessPolicy.can_access(
    dispatcher,
    make_user(Role.MANAGER, active=False),
  ) is False


def test_admin_can_access_all_users():
  admin = make_user(Role.ADMIN)
  assert UserAccessPolicy.can_access(admin, make_user(Role.CITIZEN)) is True
  assert UserAccessPolicy.can_access(admin, make_user(Role.OFFICER, active=False)) is True
