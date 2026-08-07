import pytest
from pydantic import ValidationError

from src.office.schemas import OfficeUpdate
from src.user.schemas import AdminUserUpdate, UserDeactivateRequest, UserUpdate


def test_admin_user_update_requires_change_reason():
  with pytest.raises(ValidationError):
    AdminUserUpdate(first_name="Changed")


def test_user_deactivation_requires_change_reason():
  with pytest.raises(ValidationError):
    UserDeactivateRequest()


def test_office_update_requires_change_reason():
  with pytest.raises(ValidationError):
    OfficeUpdate(description="Changed")


def test_user_updates_reject_unknown_fields_and_null_required_values():
  with pytest.raises(ValidationError):
    UserUpdate(first_name="Changed", unexpected=True)

  with pytest.raises(ValidationError):
    UserUpdate(first_name=None)

  with pytest.raises(ValidationError):
    AdminUserUpdate(role=None, change_reason="Invalid role")
