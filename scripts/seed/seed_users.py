from sqlalchemy.ext.asyncio import AsyncSession

from src.user.models import User, Role
from src.user.repository import UserRepository
from src.office.repository import OfficeRepository
from src.core.security import get_password_hash

async def run_user_seeder(db: AsyncSession):
  """
  Seeds the database with default users for each role (Admin, Manager, Officer, Citizen).
  Links the Officer to the 'Bauamt' office.
  """
  print("Seeding Users...")
  
  # Fetch an office to assign to the officer
  bauamt = await OfficeRepository.get_by_name(db, "Bauamt")
  buergeramt = await OfficeRepository.get_by_name(db, "Bürgeramt")

  default_password = get_password_hash("password123")
  
  default_users = [
    # ADMIN
    {
      "email": "admin@test.com",
      "first_name": "Armin",
      "last_name": "Admin",
      "role": Role.ADMIN,
      "office_id": None
    },
    # MANAGER
    {
      "email": "manager1@bauamt.com",
      "first_name": "Max",
      "last_name": "Manager",
      "role": Role.MANAGER,
      "office_id": bauamt.id
    },
    {
      "email": "manager2@bauamt.com",
      "first_name": "Marcus",
      "last_name": "Manager",
      "role": Role.MANAGER,
      "office_id": bauamt.id
    },
    {
      "email": "manager3@buergeramt.com",
      "first_name": "Melanie",
      "last_name": "Manager",
      "role": Role.MANAGER,
      "office_id": buergeramt.id
    },
    # DISPATCHER
    {
      "email": "dispatcher1@bauamt.com",
      "first_name": "Dave",
      "last_name": "Dispatcher",
      "role": Role.DISPATCHER,
      "office_id": bauamt.id
    },
    {
      "email": "dispatcher2@buergeramt.com",
      "first_name": "Daniel",
      "last_name": "Dispatcher",
      "role": Role.DISPATCHER,
      "office_id": buergeramt.id
    },
    {
      "email": "dispatcher3@buergeramt.com",
      "first_name": "Desiree",
      "last_name": "Dispatcher",
      "role": Role.DISPATCHER,
      "office_id": buergeramt.id
    },
    # OFFICER
    {
      "email": "officer1@bauamt.com",
      "first_name": "Olaf",
      "last_name": "Officer",
      "role": Role.OFFICER,
      "office_id": bauamt.id
    },
    {
      "email": "officer2@bauamt.com",
      "first_name": "Otto",
      "last_name": "Officer",
      "role": Role.OFFICER,
      "office_id": bauamt.id
    },
    {
      "email": "officer3@buergeramt.com",
      "first_name": "Olga",
      "last_name": "Officer",
      "role": Role.OFFICER,
      "office_id": buergeramt.id
    },
    # CITIZEN
    {
      "email": "citizen1@test.com",
      "first_name": "Celine",
      "last_name": "Citizen",
      "role": Role.CITIZEN,
      "office_id": None
    },
    {
      "email": "citizen2@test.com",
      "first_name": "Carla",
      "last_name": "Citizen",
      "role": Role.CITIZEN,
      "office_id": None
    },
    {
      "email": "citizen3@test.com",
      "first_name": "Carl",
      "last_name": "Citizen",
      "role": Role.CITIZEN,
      "office_id": None
    }
  ]
  
  
  
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
      
      print(f"  -> Created User: {new_user.email} ({new_user.role})")
    else:
      print(f"  -> Skipped: {user_data['email']} (Already exists)")