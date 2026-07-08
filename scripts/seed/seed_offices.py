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
    {
      "name": "Bauamt",
      "description": "Zuständig für Baugenehmigungen und Stadtplanung.",
      "address": {
        "street": "Rathausplatz", 
        "house_number": "1", 
        "zip_code": "12345", 
        "city": "Musterstadt", 
        "latitude": 52.5200, 
        "longitude": 13.4050
      }
    },
    {
      "name": "Bürgeramt",
      "description": "Zuständig für Meldeangelegenheiten und Ausweise.",
      "address": {
        "street": "Bahnhofstraße", 
        "house_number": "42a", 
        "zip_code": "12345", 
        "city": "Musterstadt", 
        "latitude": 52.5166, 
        "longitude": 13.3833
      }
    },
    {
      "name": "Ausländerbehörde",
      "description": "Zuständig für Aufenthalts- und Asylrecht.",
      "address": None
    }
  ]
  
  for office_data in default_offices:
    existing = await OfficeRepository.get_by_name(db, office_data["name"])
    if not existing:
      address_entity = None
      if office_data["address"]:
        address_schema = AddressCreate(**office_data["address"])
        address_entity = AddressService.create_address_entity(address_schema)
        db.add(address_entity)
        await db.flush()

      new_office = Office(
        name=office_data["name"],
        description=office_data["description"],
        address_id=address_entity.id if address_entity else None
      )
      OfficeRepository.add(db, new_office)
      await db.flush() # Flush to get the UUID for history
      
      history_entry = OfficeHistory(
        office_id=new_office.id,
        name=new_office.name,
        description=new_office.description,
        address_snapshot=OfficeService._format_address_snapshot(address_entity),
        changed_by_user_id=system_user_id,
        change_reason="System Seed: Default Office"
      )
      OfficeRepository.add_history(db, history_entry)
      addr_status = "with Address" if address_entity else "without Address"
      print(f"  -> Created Office: {new_office.name}")
    else:
      print(f"  -> Skipped: {office_data['name']} (Already exists)")