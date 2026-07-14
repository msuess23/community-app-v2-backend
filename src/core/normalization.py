from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: Any) -> str:
  """Normalize Unicode, trim surrounding whitespace, and collapse runs."""
  normalized = unicodedata.normalize("NFKC", str(value)).strip()
  return _WHITESPACE_RE.sub(" ", normalized)


def normalize_optional_text(value: Any) -> str | None:
  """Normalize optional free text and represent blank input as ``None``."""
  if value is None:
    return None
  normalized = normalize_text(value)
  return normalized or None


def normalize_email(value: Any) -> str:
  """Return the canonical representation used for email lookups."""
  return normalize_text(value).lower()


def normalize_office_name(value: Any) -> str:
  """Normalize an office display name without changing its letter case."""
  return normalize_text(value)


def normalize_string_list(value: Any) -> list[str]:
  """Normalize, deduplicate, and preserve the order of a string collection."""
  if value is None:
    return []
  if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
    return value

  normalized_values: list[str] = []
  seen: set[str] = set()
  for item in value:
    normalized = normalize_text(item)
    key = normalized.casefold()
    if key in seen:
      continue
    seen.add(key)
    normalized_values.append(normalized)
  return normalized_values
