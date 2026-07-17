import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.user.service import UserService

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def anonymization_cron_task() -> None:
  """Runs citizen-history anonymization in its own transaction."""
  async with AsyncSessionLocal() as db:
    try:
      await UserService.run_deep_anonymization(
        db,
        retention_days=settings.CITIZEN_HISTORY_RETENTION_DAYS,
      )
      await db.commit()
      logger.info("Deep anonymization completed successfully")
    except Exception:
      await db.rollback()
      logger.exception("Deep anonymization failed")


def setup_scheduler() -> None:
  """Starts the configured single-process demo scheduler."""
  global _scheduler

  if _scheduler is not None and _scheduler.running:
    return

  _scheduler = AsyncIOScheduler(timezone="UTC")
  _scheduler.add_job(
    anonymization_cron_task,
    "cron",
    hour=settings.DEEP_ANONYMIZATION_HOUR,
    minute=settings.DEEP_ANONYMIZATION_MINUTE,
    id="deep-anonymization",
    replace_existing=True,
  )
  _scheduler.start()
  logger.info(
    "Background scheduler started for %02d:%02d UTC",
    settings.DEEP_ANONYMIZATION_HOUR,
    settings.DEEP_ANONYMIZATION_MINUTE,
  )


def shutdown_scheduler() -> None:
  """Ensures a clean scheduler shutdown."""
  global _scheduler

  if _scheduler is not None and _scheduler.running:
    _scheduler.shutdown(wait=False)
  _scheduler = None
  logger.info("Background scheduler stopped")
