import asyncio
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_users import run_user_seeder
from src.core.constants import SYSTEM_USER_ID
from src.core.database import transactional_session
from src.user.models import User


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
  async with transactional_session() as db:
    system_user = await db.get(User, SYSTEM_USER_ID)
    if system_user is None:
      raise RuntimeError("System principal is missing; run Alembic migrations first")

    await run_office_seeder(db, SYSTEM_USER_ID)
    await run_user_seeder(db, SYSTEM_USER_ID)
    logger.info("Database seed process completed")


if __name__ == "__main__":
  asyncio.run(main())
