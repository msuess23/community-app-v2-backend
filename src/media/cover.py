"""Pure cover-selection rules shared by entity-specific image services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, TypeVar
from uuid import UUID


class CoverImage(Protocol):
  """Minimal mutable image shape required by the cover helpers."""

  id: UUID
  is_active: bool
  is_cover: bool


ImageT = TypeVar("ImageT", bound=CoverImage)


@dataclass(frozen=True)
class CoverChange:
  """Describe one deterministic cover transition without persistence concerns."""

  previous_cover_id: UUID | None
  new_cover_id: UUID | None

  @property
  def changed(self) -> bool:
    """Return whether the planned cover differs from the current cover."""

    return self.previous_cover_id != self.new_cover_id


def _current_cover_id(images: Sequence[CoverImage]) -> UUID | None:
  """Return the current active cover, if one exists."""

  return next(
    (image.id for image in images if image.is_active and image.is_cover),
    None,
  )


def new_image_should_be_cover(images: Sequence[CoverImage]) -> bool:
  """Use the first active image as the initial cover."""

  return not any(image.is_active for image in images)


def plan_cover_selection(
  images: Sequence[CoverImage],
  selected_image_id: UUID,
) -> CoverChange:
  """Plan an explicit cover selection for one active image.

  The caller remains responsible for translating a missing or inactive target
  into the domain-specific not-found error.
  """

  selected = next(
    (
      image
      for image in images
      if image.id == selected_image_id and image.is_active
    ),
    None,
  )
  if selected is None:
    raise ValueError("Cover selection references an unavailable image")

  return CoverChange(
    previous_cover_id=_current_cover_id(images),
    new_cover_id=selected.id,
  )


def plan_cover_after_removal(
  images: Sequence[CoverImage],
  removed_image_id: UUID,
) -> CoverChange:
  """Plan the replacement cover after one image is removed.

  Repository ordering determines the replacement. Domain repositories should
  therefore supply images in a stable order such as upload time followed by ID.
  """

  removed = next(
    (
      image
      for image in images
      if image.id == removed_image_id and image.is_active
    ),
    None,
  )
  if removed is None:
    raise ValueError("Image removal references an unavailable image")

  previous_cover_id = _current_cover_id(images)
  if not removed.is_cover:
    return CoverChange(previous_cover_id, previous_cover_id)

  replacement = next(
    (
      image.id
      for image in images
      if image.id != removed_image_id and image.is_active
    ),
    None,
  )
  return CoverChange(previous_cover_id, replacement)


def apply_cover_change(
  images: Sequence[ImageT],
  change: CoverChange,
) -> ImageT | None:
  """Apply a planned cover change to mutable projection objects.

  The helper only updates the generic ``is_cover`` flag. Event references and
  other revision metadata remain the responsibility of the owning domain.
  """

  selected: ImageT | None = None
  for image in images:
    if not image.is_active:
      image.is_cover = False
      continue
    image.is_cover = image.id == change.new_cover_id
    if image.is_cover:
      selected = image
  return selected
