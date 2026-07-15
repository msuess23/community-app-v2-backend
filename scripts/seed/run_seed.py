import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_users import run_user_seeder
from src.core.database import AsyncSessionLocal


async def main() -> None:
  """Seeds admin, offices and remaining users in one transaction."""
  print("Starting Database Seed Process...\n")

  async with AsyncSessionLocal() as db:
    try:
      admin = await run_user_seeder(db, only_admin=True)
      if admin is None:
        raise RuntimeError("Admin seed account could not be created or loaded")
      await run_office_seeder(db, admin.id)
      await run_user_seeder(db, skip_admin=True)
      await db.commit()
      print("\nDatabase Seed Process Completed Successfully.")
    except Exception as exc:
      await db.rollback()
      print(f"\nError during seeding. Transaction rolled back. Details: {exc}")


if __name__ == "__main__":
  asyncio.run(main())
