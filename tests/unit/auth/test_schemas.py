import pytest
from pydantic import ValidationError

from src.auth.schemas import ResetPasswordRequest
from src.user.schemas import UserCreate


def test_auth_payloads_normalize_email():
  reset = ResetPasswordRequest(
    email="Citizen@Example.COM",
    otp="123456",
    new_password="password123",
  )
  user = UserCreate(
    email="Citizen@Example.COM",
    password="password123",
    first_name="Test",
    last_name="User",
  )

  assert str(reset.email) == "citizen@example.com"
  assert str(user.email) == "citizen@example.com"


@pytest.mark.parametrize("otp", ["12345", "1234567", "abcdef", "12 456"])
def test_reset_otp_must_be_six_digits(otp: str):
  with pytest.raises(ValidationError):
    ResetPasswordRequest(
      email="citizen@example.com",
      otp=otp,
      new_password="password123",
    )
