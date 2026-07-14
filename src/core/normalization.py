from __future__ import annotations

import re
import unicodedata
from typing import Any


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_email(value: Any) -> str:
  """Return the canonical representation used for user identity lookups."""
  return unicodedata.normalize("NFKC", str(value)).strip().lower()


def normalize_office_name(value: Any) -> str:
  """Normalize Unicode and collapse whitespace without changing display case."""
  normalized = unicodedata.normalize("NFKC", str(value)).strip()
  return _WHITESPACE_RE.sub(" ", normalized)
