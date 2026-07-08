from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.core.database import AsyncSessionLocal
from src.user.service import UserService

# Initialize global background scheduler
scheduler = AsyncIOScheduler()

async def anonymization_cron_task():
  """
  Instantiates a database session and triggers the scheduled anonymization service.
  """
  async with AsyncSessionLocal() as db:
    try:
      await UserService.run_deep_anonymization(db)
    except Exception as e:
      print(f"Error executing deep anonymization cron task: {e}")

def setup_scheduler():
  """
  Configures and starts the background scheduler.
  """
  # Configure the task to run daily at 03:00 AM
  scheduler.add_job(anonymization_cron_task, 'cron', hour=3, minute=0)
  scheduler.start()
  print("Background scheduler started successfully.")

def shutdown_scheduler():
  """
  Ensures clean shutdown of the background scheduler.
  """
  scheduler.shutdown()
  print("Background scheduler terminated.")