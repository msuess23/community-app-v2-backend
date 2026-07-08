import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.models import User, UserHistory, Role
from src.user.repository import UserRepository
from src.office.repository import OfficeRepository
from src.core.security import get_password_hash

async def run_user_seeder(db: AsyncSession, system_user_id: uuid.UUID):
  """
  Seeds the database with default users for each role (Admin, Manager, Officer, Citizen).
  Links the Officer to the 'Bauamt' office.
  """
  print("Seeding Users...")
  
  # Fetch an office to assign to the officer
  bauamt = await OfficeRepository.get_by_name(db, "Bauamt")
  bauamt_id = bauamt.id if bauamt else None
  
  default_users = [
    {
      "email": "admin@test.com", "first_name": "System", "last_name": "Admin",
      "role": Role.ADMIN, "office_id": None
    },
    {
      "email": "manager@test.com", "first_name": "Max", "last_name": "Manager",
      "role": Role.MANAGER, "office_id": None
    },
    {
      "email": "officer@test.com", "first_name": "Olaf", "last_name": "Officer",
      "role": Role.OFFICER, "office_id": bauamt_id
    },
    {
      "email": "citizen@test.com", "first_name": "Celine", "last_name": "Citizen",
      "role": Role.CITIZEN, "office_id": None
    }
  ]
  
  default_password = get_password_hash("password123")
  
  for user_data in default_users:
    existing = await UserRepository.get_by_email(db, user_data["email"])
    if not existing:
      new_user = User(
        email=user_data["email"],
        hashed_password=default_password,
        first_name=user_data["first_name"],
        last_name=user_data["last_name"],
        role=user_data["role"],
        office_id=user_data["office_id"]
      )
      UserRepository.add(db, new_user)
      await db.flush() # Flush to get the UUID for history
      
      history_entry = UserHistory(
        user_id=new_user.id,
        email=new_user.email,
        first_name=new_user.first_name,
        last_name=new_user.last_name,
        role=new_user.role,
        changed_by_user_id=system_user_id,
        change_reason="System Seed: Default User"
      )
      UserRepository.add_history(db, history_entry)
      print(f"  -> Created User: {new_user.email} ({new_user.role})")
    else:
      print(f"  -> Skipped: {user_data['email']} (Already exists)")