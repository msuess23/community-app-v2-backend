"""Command-line and startup entry point for the complete demo data catalog."""

import asyncio
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.seed.context import load_seed_context
from scripts.seed.seed_appointments import run_appointment_seeder
from scripts.seed.seed_infos import run_info_seeder
from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_tickets import run_ticket_seeder
from scripts.seed.seed_users import run_user_seeder
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.security import ensure_bcrypt_compatible, get_password_hash
from src.core.transaction_files import (
  clear_commit_file_deletes,
  clear_rollback_files,
  cleanup_commit_file_deletes,
  cleanup_rollback_files,
)

logger = logging.getLogger(__name__)


async def seed_database() -> None:
  """Seed the complete demo catalog idempotently in one database transaction."""

  if settings.ENVIRONMENT == "production":
    raise RuntimeError("Demo seeding is disabled in production")

  if not settings.SEED_DEFAULT_PASSWORD:
    raise RuntimeError("SEED_DEFAULT_PASSWORD must be configured for demo seeding")

  seed_password = ensure_bcrypt_compatible(settings.SEED_DEFAULT_PASSWORD)
  password_hash = get_password_hash(seed_password)

  logger.info("Starting database seed process")
  async with AsyncSessionLocal() as db:
    try:
      # User and office seeds establish every role and ownership relation used
      # by the cross-domain ticket, Info, and appointment scenarios.
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
      context = await load_seed_context(db)

      # Ticket scenarios run first because one appointment intentionally links
      # to a completed ticket from the event-sourced demo history.
      await run_ticket_seeder(db, context)
      await run_info_seeder(db, context)
      await run_appointment_seeder(db, context)
      await db.commit()
    except Exception:
      await db.rollback()
      clear_commit_file_deletes(db)
      cleanup_rollback_files(db)
      logger.exception("Database seeding failed; transaction rolled back")
      raise
    else:
      # Seed uploads use the same rollback registry as HTTP requests. A durable
      # commit transfers ownership of those files to their persisted rows.
      clear_rollback_files(db)
      cleanup_commit_file_deletes(db)
      logger.info("Database seed process completed successfully")


async def main() -> None:
  """Run the asynchronous database seeder from the command line."""

  await seed_database()


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  asyncio.run(main())
