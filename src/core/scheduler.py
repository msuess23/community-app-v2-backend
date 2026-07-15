import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.database import AsyncSessionLocal
from src.user.service import UserService

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def anonymization_cron_task() -> None:
  """Runs the scheduled anonymization in its own transaction."""
  async with AsyncSessionLocal() as db:
    try:
      await UserService.run_deep_anonymization(db)
      await db.commit()
      logger.info("Deep anonymization completed successfully")
    except Exception:
      await db.rollback()
      logger.exception("Deep anonymization failed")


def setup_scheduler() -> None:
  """Configures and starts the background scheduler."""
  scheduler.add_job(
    anonymization_cron_task,
    "cron",
    hour=3,
    minute=0,
    id="deep-anonymization",
    replace_existing=True,
  )
  scheduler.start()
  logger.info("Background scheduler started")


def shutdown_scheduler() -> None:
  """Ensures clean scheduler shutdown."""
  if scheduler.running:
    scheduler.shutdown()
  logger.info("Background scheduler stopped")
