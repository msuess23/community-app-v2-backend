"""Persistence ordering for cover changes protected by partial unique indexes."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.media.cover import (
  CoverChange,
  ImageT,
  apply_cover_change,
)


async def apply_cover_change_safely(
  db: AsyncSession,
  images: Sequence[ImageT],
  change: CoverChange,
) -> ImageT | None:
  """Apply a cover transition without transiently creating two covers.

  PostgreSQL checks the partial one-cover unique index after every statement.
  Releasing the previous cover in its own flush therefore avoids depending on
  SQLAlchemy's update ordering when a different image becomes the cover.
  The caller remains responsible for the final flush after adding any
  domain-specific metadata to the selected image.
  """

  if change.changed and change.previous_cover_id is not None:
    previous = next(
      image for image in images if image.id == change.previous_cover_id
    )
    previous.is_cover = False
    await db.flush()

  return apply_cover_change(images, change)
