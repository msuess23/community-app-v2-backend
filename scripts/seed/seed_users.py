"""Seed role-specific demo users and their initial history snapshots."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from src.office.repository import OfficeRepository
from src.user.models import Role, User
from src.user.repository import UserRepository
from src.user.service import UserService

logger = logging.getLogger(__name__)


async def run_user_seeder(
  db: AsyncSession,
  *,
  password_hash: str,
  only_admin: bool = False,
  skip_admin: bool = False,
) -> User | None:
  """Seeds demo users and returns the admin account when available."""
  logger.info("Seeding users")

  bauamt = None
  buergeramt = None
  if not only_admin:
    bauamt = await OfficeRepository.get_by_name(db, "Bauamt")
    buergeramt = await OfficeRepository.get_by_name(db, "Bürgeramt")

    if bauamt is None or buergeramt is None:
      raise RuntimeError("Required seed offices are missing")

  default_users = [
    {
      "email": "admin@test.com",
      "first_name": "Armin",
      "last_name": "Admin",
      "role": Role.ADMIN,
      "office_id": None,
    },
  ]

  if not only_admin:
    default_users.extend(
      [
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
    )

  admin: User | None = None
  for user_data in default_users:
    if skip_admin and user_data["role"] == Role.ADMIN:
      continue

    existing = await UserRepository.get_by_email(db, user_data["email"])
    if existing:
      if existing.role == Role.ADMIN:
        admin = existing
      logger.info("Skipped existing user: %s", user_data["email"])
      continue

    new_user = User(
      email=user_data["email"],
      hashed_password=password_hash,
      first_name=user_data["first_name"],
      last_name=user_data["last_name"],
      role=user_data["role"],
      office_id=user_data["office_id"],
    )
    UserRepository.add(db, new_user)
    await db.flush()
    UserService.add_history_snapshot(
      db,
      new_user,
      changed_by_user_id=new_user.id,
      change_reason="USER_SEEDED",
    )
    await db.flush()

    if new_user.role == Role.ADMIN:
      admin = new_user
    logger.info("Created user: %s (%s)", new_user.email, new_user.role)

  return admin
