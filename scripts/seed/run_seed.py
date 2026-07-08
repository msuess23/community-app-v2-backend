import asyncio
import sys
import os
import uuid

# Ensure the script can import the src module from the root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.database import AsyncSessionLocal
from scripts.seed.seed_offices import run_office_seeder
from scripts.seed.seed_users import run_user_seeder

async def main():
  """
  Main orchestrator for database seeding.
  Executes individual seeders in the correct dependency order.
  """
  print("Starting Database Seed Process...\n")
  
  # A dummy UUID to represent the "System" executing the initial seeds
  system_user_id = uuid.uuid4()
  
  async with AsyncSessionLocal() as db:
    try:
      # 1. Seed independent entities (Offices)
      await run_office_seeder(db, system_user_id)
      
      # 2. Seed dependent entities (Users depend on Offices)
      await run_user_seeder(db, system_user_id)
      
      # 3. Future: Seed Tickets (depend on Users and Offices)
      # await run_ticket_seeder(db, system_user_id)
      
      # Commit all seeded data atomically
      await db.commit()
      print("\nDatabase Seed Process Completed Successfully.")
      
    except Exception as e:
      await db.rollback()
      print(f"\nError during seeding. Transaction rolled back. Details: {e}")

if __name__ == "__main__":
  asyncio.run(main())