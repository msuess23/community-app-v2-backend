"""Seed demo offices, owned addresses, and initial history snapshots."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.schemas import AddressCreate
from src.address.service import AddressService
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.office.service import OfficeService

logger = logging.getLogger(__name__)


async def run_office_seeder(db: AsyncSession, admin_id: uuid.UUID) -> None:
  """Seeds default offices, including their initial history snapshots."""
  logger.info("Seeding offices")

  default_offices = [
    {
      "name": "Bauamt",
      "description": "Zuständig für Baugenehmigungen und Stadtplanung.",
      "contact_email": "bauamt@example.com",
      "phone": "+49 30 123456",
      "services": ["Baugenehmigung", "Stadtplanung"],
      "opening_hours": {
        "monday": "08:00-12:00",
        "tuesday": "08:00-12:00",
        "wednesday": "08:00-12:00",
        "thursday": "13:00-18:00",
        "friday": "08:00-12:00",
      },
      "address": {
        "street": "Rathausplatz",
        "house_number": "1",
        "zip_code": "12345",
        "city": "Musterstadt",
        "latitude": 52.5200,
        "longitude": 13.4050,
      },
    },
    {
      "name": "Bürgeramt",
      "description": "Zuständig für Meldeangelegenheiten und Ausweise.",
      "contact_email": "buergeramt@example.com",
      "phone": "+49 30 987654",
      "services": ["Personalausweis", "Reisepass", "Ummeldung"],
      "opening_hours": {
        "monday": "07:30-15:00",
        "tuesday": "07:30-15:00",
        "wednesday": "07:30-13:00",
        "thursday": "10:00-18:00",
        "friday": "07:30-12:00",
      },
      "address": {
        "street": "Bahnhofstraße",
        "house_number": "42a",
        "zip_code": "12345",
        "city": "Musterstadt",
        "latitude": 52.5166,
        "longitude": 13.3833,
      },
    },
    {
      "name": "Ausländerbehörde",
      "description": "Zuständig für Aufenthalts- und Asylrecht.",
      "address": None,
    },
  ]

  for office_data in default_offices:
    existing = await OfficeRepository.get_by_name(db, office_data["name"])
    if existing:
      logger.info("Skipped existing office: %s", office_data["name"])
      continue

    address_entity = None
    if office_data["address"]:
      address_entity = AddressService.create_address_entity(
        AddressCreate(**office_data["address"])
      )
      db.add(address_entity)
      await db.flush()

    new_office = Office(
      name=office_data["name"],
      description=office_data["description"],
      contact_email=office_data.get("contact_email"),
      phone=office_data.get("phone"),
      services=office_data.get("services", []),
      opening_hours=office_data.get("opening_hours", {}),
      address=address_entity,
    )
    OfficeRepository.add(db, new_office)
    await db.flush()
    OfficeService.add_history_snapshot(
      db,
      new_office,
      changed_by_user_id=admin_id,
      change_reason="OFFICE_SEEDED",
    )
    await db.flush()
    logger.info("Created office: %s", new_office.name)
