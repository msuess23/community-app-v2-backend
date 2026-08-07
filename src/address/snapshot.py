"""Shared immutable address snapshot used by histories and event payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AddressSnapshot(BaseModel):
  """Represent an address value at one historical point in time."""

  street: str | None = None
  house_number: str | None = None
  zip_code: str | None = None
  city: str | None = None
  latitude: float | None = None
  longitude: float | None = None
  formatted: str | None = None

  @classmethod
  def from_address(cls, address: Any | None) -> "AddressSnapshot | None":
    """Create a structured snapshot from an ORM entity or compatible object."""

    if address is None:
      return None
    return cls(
      street=address.street,
      house_number=address.house_number,
      zip_code=address.zip_code,
      city=address.city,
      latitude=address.latitude,
      longitude=address.longitude,
      formatted=(
        f"{address.street} {address.house_number}, "
        f"{address.zip_code} {address.city}"
      ),
    )
