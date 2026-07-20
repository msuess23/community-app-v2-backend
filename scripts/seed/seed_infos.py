"""Seed mutable Info CRUD rows with varied statuses, addresses, and images."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed.context import SeedContext
from scripts.seed.media_factory import image_upload
from src.address.schemas import AddressCreate
from src.info.image_service import InfoImageService
from src.info.models import Info, InfoCategory, InfoStatus
from src.info.schemas import (
  InfoCreateRequest,
  InfoImageResponse,
  InfoStatusCreateRequest,
  InfoUpdateRequest,
)
from src.info.service import InfoService
from src.user.models import User

logger = logging.getLogger(__name__)

INFO_SEED_TITLES = (
  "[Demo] Sommerfest am Rathaus",
  "[Demo] Sperrung der Parkstraße",
  "[Demo] Wartung des Bürgerportals",
  "[Demo] Geänderte Öffnungszeiten",
  "[Demo] Mobile Beratungsstelle",
  "[Demo] Abgesagte Informationsveranstaltung",
)


async def _find_info(db: AsyncSession, title: str) -> Info | None:
  """Load a previously seeded Info notice by its stable demo title."""

  result = await db.execute(select(Info).where(Info.title == title).limit(1))
  return result.scalar_one_or_none()


async def _add_info_image(
  db: AsyncSession,
  *,
  info: Info,
  actor: User,
  filename: str,
  rgb: tuple[int, int, int],
) -> InfoImageResponse:
  """Attach one generated PNG through the ordinary Info image service."""

  upload = image_upload(filename, rgb=rgb)
  try:
    return await InfoImageService.add_image(db, info.id, upload, actor)
  finally:
    await upload.close()


async def _create_info(
  db: AsyncSession,
  *,
  actor: User,
  title: str,
  description: str,
  category: InfoCategory,
  starts_at: datetime,
  ends_at: datetime,
  office_id: uuid.UUID | None = None,
  address: AddressCreate | None = None,
) -> Info:
  """Create one Info notice through the canonical CRUD service."""

  await InfoService.create_info(
    db,
    InfoCreateRequest(
      title=title,
      description=description,
      category=category,
      office_id=office_id,
      address=address,
      starts_at=starts_at,
      ends_at=ends_at,
    ),
    actor,
  )
  info = await _find_info(db, title)
  if info is None:
    raise RuntimeError(f"Seed Info was not persisted: {title}")
  return info


async def _set_status(
  db: AsyncSession,
  *,
  info: Info,
  actor: User,
  status: InfoStatus,
  message: str,
) -> None:
  """Append one status history row through the canonical Info service."""

  await InfoService.add_status(
    db,
    info.id,
    InfoStatusCreateRequest(status=status, message=message),
    actor,
  )


async def run_info_seeder(db: AsyncSession, context: SeedContext) -> None:
  """Seed Info CRUD examples across categories, offices, and lifecycle states."""

  logger.info("Seeding Info scenarios")
  now = datetime.now(timezone.utc)
  admin = context.user("admin@test.com")
  manager1 = context.user("manager1@bauamt.com")
  manager3 = context.user("manager3@buergeramt.com")
  bauamt = context.office("Bauamt")
  buergeramt = context.office("Bürgeramt")

  if await _find_info(db, INFO_SEED_TITLES[0]) is None:
    info = await _create_info(
      db,
      actor=manager1,
      title=INFO_SEED_TITLES[0],
      description="Public summer festival with local associations and family activities.",
      category=InfoCategory.EVENT,
      office_id=bauamt.id,
      address=AddressCreate(
        street="Rathausplatz",
        house_number="1",
        zip_code="12345",
        city="Musterstadt",
        latitude=52.5200,
        longitude=13.4050,
      ),
      starts_at=now + timedelta(days=21),
      ends_at=now + timedelta(days=21, hours=8),
    )
    first = await _add_info_image(
      db,
      info=info,
      actor=manager1,
      filename="summer-festival-stage.png",
      rgb=(239, 189, 83),
    )
    second = await _add_info_image(
      db,
      info=info,
      actor=manager1,
      filename="summer-festival-poster.png",
      rgb=(79, 134, 198),
    )
    await InfoImageService.set_cover(db, info.id, second.id, manager1)
    logger.info("Created scheduled Info with images %s and %s", first.id, second.id)

  if await _find_info(db, INFO_SEED_TITLES[1]) is None:
    info = await _create_info(
      db,
      actor=manager1,
      title=INFO_SEED_TITLES[1],
      description="Road works temporarily close Parkstraße to through traffic.",
      category=InfoCategory.CONSTRUCTION,
      office_id=bauamt.id,
      address=AddressCreate(
        street="Parkstraße",
        house_number="20",
        zip_code="12345",
        city="Musterstadt",
        latitude=52.5193,
        longitude=13.3982,
      ),
      starts_at=now - timedelta(days=2),
      ends_at=now + timedelta(days=12),
    )
    await _set_status(
      db,
      info=info,
      actor=manager1,
      status=InfoStatus.ACTIVE,
      message="The road closure is currently in effect.",
    )
    await InfoService.update_info(
      db,
      info.id,
      InfoUpdateRequest(
        description=(
          "Road works temporarily close Parkstraße to through traffic. "
          "Local access remains possible from the northern junction."
        )
      ),
      manager1,
    )
    await _add_info_image(
      db,
      info=info,
      actor=manager1,
      filename="road-closure-map.png",
      rgb=(215, 92, 71),
    )

  if await _find_info(db, INFO_SEED_TITLES[2]) is None:
    info = await _create_info(
      db,
      actor=manager3,
      title=INFO_SEED_TITLES[2],
      description="Scheduled maintenance of the online appointment portal.",
      category=InfoCategory.MAINTENANCE,
      office_id=buergeramt.id,
      starts_at=now - timedelta(days=10),
      ends_at=now - timedelta(days=9, hours=20),
    )
    await _set_status(
      db,
      info=info,
      actor=manager3,
      status=InfoStatus.ACTIVE,
      message="Maintenance started as announced.",
    )
    await _set_status(
      db,
      info=info,
      actor=manager3,
      status=InfoStatus.DONE,
      message="The portal is available again.",
    )

  if await _find_info(db, INFO_SEED_TITLES[3]) is None:
    info = await _create_info(
      db,
      actor=manager3,
      title=INFO_SEED_TITLES[3],
      description="Thursday service hours are extended for the next four weeks.",
      category=InfoCategory.ANNOUNCEMENT,
      office_id=buergeramt.id,
      starts_at=now - timedelta(days=1),
      ends_at=now + timedelta(days=28),
    )
    await _set_status(
      db,
      info=info,
      actor=manager3,
      status=InfoStatus.ACTIVE,
      message="Extended opening hours are now active.",
    )

  if await _find_info(db, INFO_SEED_TITLES[4]) is None:
    info = await _create_info(
      db,
      actor=admin,
      title=INFO_SEED_TITLES[4],
      description="A cross-office mobile consultation service visits outlying districts.",
      category=InfoCategory.OTHER,
      starts_at=now + timedelta(days=7),
      ends_at=now + timedelta(days=35),
      address=AddressCreate(
        street="Marktplatz",
        house_number="7",
        zip_code="12346",
        city="Musterstadt-Nord",
        latitude=52.5480,
        longitude=13.3920,
      ),
    )
    await _add_info_image(
      db,
      info=info,
      actor=admin,
      filename="mobile-consultation.png",
      rgb=(69, 160, 139),
    )

  if await _find_info(db, INFO_SEED_TITLES[5]) is None:
    info = await _create_info(
      db,
      actor=manager3,
      title=INFO_SEED_TITLES[5],
      description="The planned evening information event cannot take place.",
      category=InfoCategory.EVENT,
      office_id=buergeramt.id,
      starts_at=now + timedelta(days=4),
      ends_at=now + timedelta(days=4, hours=2),
    )
    await _set_status(
      db,
      info=info,
      actor=manager3,
      status=InfoStatus.CANCELLED,
      message="The event was cancelled because the venue is unavailable.",
    )

  logger.info("Info scenario seeding completed")
