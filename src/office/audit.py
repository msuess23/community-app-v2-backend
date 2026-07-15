import uuid
from datetime import datetime
from typing import Any

from src.address.models import Address
from src.office.models import Office, OfficeHistory


def build_address_snapshot(address: Address | None) -> dict[str, Any] | None:
  """Serialize every revision-relevant address field into structured JSON."""
  if address is None:
    return None
  return {
    "id": str(address.id) if address.id is not None else None,
    "street": address.street,
    "house_number": address.house_number,
    "zip_code": address.zip_code,
    "city": address.city,
    "latitude": address.latitude,
    "longitude": address.longitude,
  }


def build_office_history(
  office: Office,
  *,
  actor_id: uuid.UUID,
  change_reason: str,
  valid_to: datetime,
) -> OfficeHistory:
  """Archive the office state that was valid immediately before a change."""
  valid_from = office.updated_at or office.created_at or valid_to
  return OfficeHistory(
    office_id=office.id,
    name=office.name,
    description=office.description,
    contact_email=office.contact_email,
    phone=office.phone,
    services=list(office.services or []),
    opening_hours=dict(office.opening_hours or {}),
    address_snapshot=build_address_snapshot(office.address),
    is_active=office.is_active,
    deactivated_at=office.deactivated_at,
    valid_from=valid_from,
    valid_to=valid_to,
    changed_by_user_id=actor_id,
    change_reason=change_reason,
  )
