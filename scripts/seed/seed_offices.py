import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.address.service import AddressService
from src.office.models import Office
from src.office.repository import OfficeRepository
from src.office.schemas import OfficeCreate


logger = logging.getLogger(__name__)


def _open(start: str, end: str) -> list[dict[str, str]]:
  return [{"start": start, "end": end}]


async def run_office_seeder(db: AsyncSession) -> None:
  """Seed default offices using validated domain payloads."""
  default_offices = [
    {
      "name": "Bauamt",
      "description": "Zuständig für Baugenehmigungen und Stadtplanung.",
      "contact_email": "bauamt@example.com",
      "phone": "+49 30 123456",
      "services": ["Baugenehmigung", "Stadtplanung"],
      "opening_hours": {
        "monday": _open("08:00", "12:00"),
        "tuesday": _open("08:00", "12:00"),
        "wednesday": _open("08:00", "12:00"),
        "thursday": _open("13:00", "18:00"),
        "friday": _open("08:00", "12:00"),
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
        "monday": _open("07:30", "15:00"),
        "tuesday": _open("07:30", "15:00"),
        "wednesday": _open("07:30", "13:00"),
        "thursday": _open("10:00", "18:00"),
        "friday": _open("07:30", "12:00"),
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

  for raw_office_data in default_offices:
    office_data = OfficeCreate(**raw_office_data)
    existing = await OfficeRepository.get_by_name(db, office_data.name)
    if existing is not None:
      logger.info("Skipped existing seed office", extra={"office": office_data.name})
      continue

    address_entity = (
      AddressService.create_address_entity(office_data.address)
      if office_data.address is not None
      else None
    )
    now = datetime.now(timezone.utc)
    new_office = Office(
      name=office_data.name,
      description=office_data.description,
      contact_email=(
        str(office_data.contact_email)
        if office_data.contact_email is not None
        else None
      ),
      phone=office_data.phone,
      services=list(office_data.services),
      opening_hours=office_data.opening_hours.model_dump(mode="json"),
      address=address_entity,
      created_at=now,
      updated_at=now,
    )
    OfficeRepository.add(db, new_office)
    await db.flush()
    logger.info("Created seed office", extra={"office": new_office.name})
