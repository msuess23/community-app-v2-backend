"""Regression checks for response relationships in async SQLAlchemy code."""

from src.info.models import Info
from src.office.models import Office
from src.ticket.models import Ticket


def test_response_relationships_never_issue_implicit_sql() -> None:
  """Keep response-facing relationships on explicit eager-loading paths."""

  assert Ticket.address.property.lazy == "raise_on_sql"
  assert Ticket.images.property.lazy == "raise_on_sql"
  assert Info.address.property.lazy == "raise_on_sql"
  assert Info.images.property.lazy == "raise_on_sql"
  assert Office.address.property.lazy == "raise_on_sql"
