import asyncio
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_users import run_user_seeder
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.security import ensure_bcrypt_compatible, get_password_hash

logger = logging.getLogger(__name__)


async def seed_database() -> None:
  """Seeds demo data idempotently in one transaction."""
  if settings.ENVIRONMENT == "production":
    raise RuntimeError("Demo seeding is disabled in production")

  if not settings.SEED_DEFAULT_PASSWORD:
    raise RuntimeError("SEED_DEFAULT_PASSWORD must be configured for demo seeding")

  seed_password = ensure_bcrypt_compatible(settings.SEED_DEFAULT_PASSWORD)
  password_hash = get_password_hash(seed_password)

  logger.info("Starting database seed process")
  async with AsyncSessionLocal() as db:
    try:
      admin = await run_user_seeder(
        db,
        password_hash=password_hash,
        only_admin=True,
      )
      if admin is None:
        raise RuntimeError("Admin seed account could not be created or loaded")

      await run_office_seeder(db, admin.id)
      await run_user_seeder(
        db,
        password_hash=password_hash,
        skip_admin=True,
      )
      await db.commit()
      logger.info("Database seed process completed successfully")
    except Exception:
      await db.rollback()
      logger.exception("Database seeding failed; transaction rolled back")
      raise


async def main() -> None:
  await seed_database()


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  asyncio.run(main())
