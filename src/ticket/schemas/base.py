"""Ticket aliases for reusable API naming and text-normalization helpers."""

from src.core.api_models import CamelCaseApiModel, to_camel
from src.core.validation import normalize_optional_text, normalize_required_text

_to_camel = to_camel
_normalize_required_text = normalize_required_text
_normalize_optional_text = normalize_optional_text


class TicketApiModel(CamelCaseApiModel):
  """Maintains the established ticket schema base name for compatibility."""
