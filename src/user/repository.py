from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.user.models import User

async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
  """Fetches a user by email for authentication purposes."""
  result = await db.execute(select(User).where(User.email == email))
  return result.scalar_one_or_none()

async def create_user(db: AsyncSession, user_data: dict) -> User:
  """Creates a new user record."""
  new_user = User(**user_data)
  db.add(new_user)
  await db.commit()
  await db.refresh(new_user)
  return new_user