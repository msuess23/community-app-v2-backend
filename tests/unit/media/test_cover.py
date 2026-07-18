from dataclasses import dataclass
from uuid import UUID, uuid4

from src.media.cover import (
  apply_cover_change,
  new_image_should_be_cover,
  plan_cover_after_removal,
  plan_cover_selection,
)


@dataclass
class _Image:
  id: UUID
  is_active: bool = True
  is_cover: bool = False


def test_first_active_image_becomes_cover() -> None:
  assert new_image_should_be_cover([]) is True
  assert new_image_should_be_cover([_Image(uuid4())]) is False
  assert new_image_should_be_cover([_Image(uuid4(), is_active=False)]) is True


def test_explicit_cover_selection_is_applied_to_one_image() -> None:
  first = _Image(uuid4(), is_cover=True)
  second = _Image(uuid4())

  change = plan_cover_selection([first, second], second.id)
  selected = apply_cover_change([first, second], change)

  assert change.previous_cover_id == first.id
  assert change.new_cover_id == second.id
  assert first.is_cover is False
  assert second.is_cover is True
  assert selected is second


def test_removing_cover_chooses_first_remaining_active_image() -> None:
  first = _Image(uuid4(), is_cover=True)
  second = _Image(uuid4())
  third = _Image(uuid4())

  change = plan_cover_after_removal([first, second, third], first.id)
  first.is_active = False
  selected = apply_cover_change([first, second, third], change)

  assert change.new_cover_id == second.id
  assert first.is_cover is False
  assert second.is_cover is True
  assert third.is_cover is False
  assert selected is second
