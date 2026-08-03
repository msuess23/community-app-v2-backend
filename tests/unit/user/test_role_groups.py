"""Regression coverage for endpoint-specific user role groups."""

from src.user.models import Role
from src.user.roles import AUTHORITY_ROLES, USER_DIRECTORY_ROLES


def test_user_directory_roles_include_admin_without_expanding_workflow_roles():
  """Allow admins to list users without granting them authority workflow access."""

  assert USER_DIRECTORY_ROLES == {*AUTHORITY_ROLES, Role.ADMIN}
  assert Role.ADMIN not in AUTHORITY_ROLES
  assert Role.CITIZEN not in USER_DIRECTORY_ROLES
