import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_users import run_user_seeder
from src.core.database import AsyncSessionLocal


async def main():
  """Seeds offices first and users second in one transaction."""
  print("Starting Database Seed Process...\n")

  async with AsyncSessionLocal() as db:
    try:
      await run_office_seeder(db)
      await run_user_seeder(db)
      await db.commit()
      print("\nDatabase Seed Process Completed Successfully.")
    except Exception as exc:
      await db.rollback()
      print(f"\nError during seeding. Transaction rolled back. Details: {exc}")


if __name__ == "__main__":
  asyncio.run(main())
