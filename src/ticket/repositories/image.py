"""Queries for revisioned ticket-image projections."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.ticket.models import TicketImage

class TicketImageRepository:
  """Persists and queries ticket image metadata."""

  @staticmethod
  def add_image(db: AsyncSession, image: TicketImage) -> None:
    """Stages one ticket-image projection row."""

    db.add(image)

  @staticmethod
  async def get_image(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    image_id: uuid.UUID,
    *,
    for_update: bool = False,
  ) -> TicketImage | None:
    """Loads one image that belongs to a ticket, optionally with a row lock."""

    query = select(TicketImage).where(
      TicketImage.id == image_id,
      TicketImage.ticket_id == ticket_id,
    )
    if for_update:
      query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()

  @staticmethod
  async def get_images(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    *,
    include_removed: bool = False,
    for_update: bool = False,
  ) -> list[TicketImage]:
    """Lists image projections in upload order."""

    query = select(TicketImage).where(TicketImage.ticket_id == ticket_id)
    if not include_removed:
      query = query.where(TicketImage.is_active.is_(True))
    if for_update:
      query = query.with_for_update()
    result = await db.execute(
      query.order_by(TicketImage.uploaded_at.asc(), TicketImage.id.asc())
    )
    return list(result.scalars().all())
