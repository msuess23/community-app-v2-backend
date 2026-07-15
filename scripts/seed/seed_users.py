import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.normalization import normalize_email
from src.core.security import get_password_hash
from src.office.repository import OfficeRepository
from src.user.models import Role, User
from src.user.repository import UserRepository


logger = logging.getLogger(__name__)


async def run_user_seeder(db: AsyncSession) -> None:
  """Seed development users with valid role/office assignments."""
  bauamt = await OfficeRepository.get_by_name(db, "Bauamt")
  buergeramt = await OfficeRepository.get_by_name(db, "Bürgeramt")
  if bauamt is None or buergeramt is None:
    raise RuntimeError("Required seed offices are missing")

  if settings.SEED_DEFAULT_PASSWORD is None:
    raise RuntimeError("SEED_DEFAULT_PASSWORD is required for development seeding")
  default_password = get_password_hash(settings.SEED_DEFAULT_PASSWORD)
  default_users = [
    {
      "email": "admin@test.com",
      "first_name": "Armin",
      "last_name": "Admin",
      "role": Role.ADMIN,
      "office_id": None,
    },
    {
      "email": "manager1@bauamt.com",
      "first_name": "Max",
      "last_name": "Manager",
      "role": Role.MANAGER,
      "office_id": bauamt.id,
    },
    {
      "email": "manager2@bauamt.com",
      "first_name": "Marcus",
      "last_name": "Manager",
      "role": Role.MANAGER,
      "office_id": bauamt.id,
    },
    {
      "email": "manager3@buergeramt.com",
      "first_name": "Melanie",
      "last_name": "Manager",
      "role": Role.MANAGER,
      "office_id": buergeramt.id,
    },
    {
      "email": "dispatcher1@bauamt.com",
      "first_name": "Dave",
      "last_name": "Dispatcher",
      "role": Role.DISPATCHER,
      "office_id": bauamt.id,
    },
    {
      "email": "dispatcher2@buergeramt.com",
      "first_name": "Daniel",
      "last_name": "Dispatcher",
      "role": Role.DISPATCHER,
      "office_id": buergeramt.id,
    },
    {
      "email": "dispatcher3@buergeramt.com",
      "first_name": "Desiree",
      "last_name": "Dispatcher",
      "role": Role.DISPATCHER,
      "office_id": buergeramt.id,
    },
    {
      "email": "officer1@bauamt.com",
      "first_name": "Olaf",
      "last_name": "Officer",
      "role": Role.OFFICER,
      "office_id": bauamt.id,
    },
    {
      "email": "officer2@bauamt.com",
      "first_name": "Otto",
      "last_name": "Officer",
      "role": Role.OFFICER,
      "office_id": bauamt.id,
    },
    {
      "email": "officer3@buergeramt.com",
      "first_name": "Olga",
      "last_name": "Officer",
      "role": Role.OFFICER,
      "office_id": buergeramt.id,
    },
    {
      "email": "citizen1@test.com",
      "first_name": "Celine",
      "last_name": "Citizen",
      "role": Role.CITIZEN,
      "office_id": None,
    },
    {
      "email": "citizen2@test.com",
      "first_name": "Carla",
      "last_name": "Citizen",
      "role": Role.CITIZEN,
      "office_id": None,
    },
    {
      "email": "citizen3@test.com",
      "first_name": "Carl",
      "last_name": "Citizen",
      "role": Role.CITIZEN,
      "office_id": None,
    },
  ]

  for user_data in default_users:
    email = normalize_email(user_data["email"])
    if await UserRepository.get_by_email(db, email):
      logger.info("Skipped existing seed user", extra={"email": email})
      continue

    now = datetime.now(timezone.utc)
    new_user = User(
      email=email,
      hashed_password=default_password,
      first_name=user_data["first_name"],
      last_name=user_data["last_name"],
      role=user_data["role"],
      office_id=user_data["office_id"],
      created_at=now,
      updated_at=now,
    )
    UserRepository.add(db, new_user)
    await db.flush()
    logger.info("Created seed user", extra={"email": new_user.email})
