"""Cross-domain guards that protect scheduled appointment commitments."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.appointment.repository import AppointmentRepository, AppointmentSlotRepository
from src.core.exceptions import ConflictException


class AppointmentLifecycleGuard:
  """Prevent lifecycle changes from orphaning future appointment data."""

  @staticmethod
  async def ensure_user_has_no_scheduled_appointments(
    db: AsyncSession,
    user_id: uuid.UUID,
  ) -> None:
    """Reject user deactivation while the citizen owns a scheduled appointment."""

    if await AppointmentRepository.has_scheduled_for_citizen(db, user_id):
      raise ConflictException(
        "User cannot be deactivated while scheduled appointments exist.",
        error_code="USER_HAS_SCHEDULED_APPOINTMENTS",
      )

  @staticmethod
  async def ensure_office_has_no_appointment_commitments(
    db: AsyncSession,
    office_id: uuid.UUID,
  ) -> None:
    """Reject office deactivation while slots or scheduled appointments remain."""

    has_scheduled = await AppointmentRepository.has_scheduled_for_office(db, office_id)
    has_capacity = await AppointmentSlotRepository.has_future_available_slots(
      db,
      office_id,
    )
    if has_scheduled or has_capacity:
      raise ConflictException(
        "Office cannot be deactivated while appointment commitments exist.",
        error_code="OFFICE_HAS_APPOINTMENT_COMMITMENTS",
      )
