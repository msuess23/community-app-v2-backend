"""Reusable normalization types and helpers for user-supplied text."""

from typing import Annotated

from pydantic import BeforeValidator, Field


def normalize_required_text(value: str) -> str:
  """Collapse whitespace and reject text containing no visible characters."""

  normalized = " ".join(value.split())
  if not normalized:
    raise ValueError("value must not be blank")
  return normalized


def normalize_optional_text(value: str | None) -> str | None:
  """Collapse whitespace and convert optional blank text to null."""

  if value is None:
    return None
  normalized = " ".join(value.split())
  return normalized or None


def normalize_non_nullable_update_text(value: str | None) -> str:
  """Normalize a supplied PATCH string while rejecting an explicit null."""

  if value is None:
    raise ValueError("value cannot be null")
  return normalize_required_text(value)


NormalizedRequiredText = Annotated[str, BeforeValidator(normalize_required_text)]
NormalizedOptionalText = Annotated[
  str | None,
  BeforeValidator(normalize_optional_text),
]
NonNullableNormalizedUpdateText = Annotated[
  str | None,
  BeforeValidator(normalize_non_nullable_update_text),
]
ChangeReason = Annotated[
  NormalizedRequiredText,
  Field(min_length=3, max_length=500),
]
