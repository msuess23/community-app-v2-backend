import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from src.office.models import Office, OfficeHistory
from src.office.repository import OfficeRepository

async def run_office_seeder(db: AsyncSession, system_user_id: uuid.UUID):
  """
  Seeds the database with default offices if they do not exist.
  """
  print("Seeding Offices...")
  
  default_offices = [
    {"name": "Bauamt", "description": "Zuständig für Baugenehmigungen und Stadtplanung."},
    {"name": "Bürgeramt", "description": "Zuständig für Meldeangelegenheiten und Ausweise."},
    {"name": "Ausländerbehörde", "description": "Zuständig für Aufenthalts- und Asylrecht."}
  ]
  
  for office_data in default_offices:
    existing = await OfficeRepository.get_by_name(db, office_data["name"])
    if not existing:
      new_office = Office(
        name=office_data["name"],
        description=office_data["description"]
      )
      OfficeRepository.add(db, new_office)
      await db.flush() # Flush to get the UUID for history
      
      history_entry = OfficeHistory(
        office_id=new_office.id,
        name=new_office.name,
        description=new_office.description,
        changed_by_user_id=system_user_id,
        change_reason="System Seed: Default Office"
      )
      OfficeRepository.add_history(db, history_entry)
      print(f"  -> Created Office: {new_office.name}")
    else:
      print(f"  -> Skipped: {office_data['name']} (Already exists)")