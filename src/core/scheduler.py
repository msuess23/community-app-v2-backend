import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.database import transactional_session
from src.user.service import UserService


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def anonymization_cron_task() -> None:
  """Execute deep anonymization within one atomic transaction."""
  try:
    async with transactional_session() as db:
      await UserService.run_deep_anonymization(db)
  except Exception:
    logger.exception("Deep anonymization cron task failed")


def setup_scheduler() -> None:
  """Configure and start the process-local scheduler."""
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
  """Stop the scheduler when it is running."""
  if scheduler.running:
    scheduler.shutdown()
    logger.info("Background scheduler stopped")
