"""Shared lookup context for cross-domain demo seeders."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.office.models import Office
from src.office.repository import OfficeRepository
from src.user.models import User
from src.user.repository import UserRepository


@dataclass(frozen=True)
class SeedContext:
  """Hold the offices and users referenced by deterministic seed scenarios."""

  offices: dict[str, Office]
  users: dict[str, User]

  def office(self, name: str) -> Office:
    """Return a required seed office by its stable name."""

    return self.offices[name]

  def user(self, email: str) -> User:
    """Return a required seed user by its stable email address."""

    return self.users[email]


async def load_seed_context(db: AsyncSession) -> SeedContext:
  """Load every office and user required by the domain seed catalog."""

  office_names = ("Bauamt", "Bürgeramt", "Ausländerbehörde")
  user_emails = (
    "admin@test.com",
    "manager1@bauamt.com",
    "manager2@bauamt.com",
    "manager3@buergeramt.com",
    "dispatcher1@bauamt.com",
    "dispatcher2@buergeramt.com",
    "officer1@bauamt.com",
    "officer2@bauamt.com",
    "officer3@buergeramt.com",
    "citizen1@test.com",
    "citizen2@test.com",
    "citizen3@test.com",
  )

  offices: dict[str, Office] = {}
  for name in office_names:
    office = await OfficeRepository.get_by_name(db, name)
    if office is None:
      raise RuntimeError(f"Required seed office is missing: {name}")
    offices[name] = office

  users: dict[str, User] = {}
  for email in user_emails:
    user = await UserRepository.get_by_email(db, email)
    if user is None:
      raise RuntimeError(f"Required seed user is missing: {email}")
    users[email] = user

  return SeedContext(offices=offices, users=users)
