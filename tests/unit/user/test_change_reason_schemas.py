import pytest
from pydantic import ValidationError

from src.office.schemas import OfficeUpdate
from src.user.schemas import AdminUserUpdate, UserDeactivateRequest


def test_admin_user_update_requires_change_reason():
  with pytest.raises(ValidationError):
    AdminUserUpdate(first_name="Changed")


def test_user_deactivation_requires_change_reason():
  with pytest.raises(ValidationError):
    UserDeactivateRequest()


def test_office_update_requires_change_reason():
  with pytest.raises(ValidationError):
    OfficeUpdate(description="Changed")
