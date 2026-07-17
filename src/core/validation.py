"""Small reusable normalization helpers for user-supplied text."""


def normalize_required_text(value: str) -> str:
  """Collapses whitespace and rejects text containing no visible characters."""

  normalized = " ".join(value.split())
  if not normalized:
    raise ValueError("value must not be blank")
  return normalized


def normalize_optional_text(value: str | None) -> str | None:
  """Collapses whitespace and converts optional blank text to null."""

  if value is None:
    return None
  normalized = " ".join(value.split())
  return normalized or None
