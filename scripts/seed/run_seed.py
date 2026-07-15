import asyncio
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_users import run_user_seeder
from src.core.config import settings
from src.core.database import transactional_session


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
  if settings.ENVIRONMENT == "production":
    raise RuntimeError("Development seed data must not be created in production")
  if settings.SEED_DEFAULT_PASSWORD is None:
    raise RuntimeError("SEED_DEFAULT_PASSWORD is required for development seeding")

  async with transactional_session() as db:
    await run_office_seeder(db)
    await run_user_seeder(db)
    logger.info("Database seed process completed")


if __name__ == "__main__":
  asyncio.run(main())
