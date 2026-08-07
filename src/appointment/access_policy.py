"""Central authorization rules for appointment slots and bookings."""

from __future__ import annotations

from src.appointment.models import Appointment
from src.user.models import Role, User
from src.user.roles import CASE_WORKER_ROLES


class AppointmentAccessPolicy:
  """Evaluate object-level appointment and slot permissions."""

  @staticmethod
  def can_manage_office(office_id, current_user: User) -> bool:
    """Return whether a case worker may manage one office's appointments."""

    return (
      current_user.is_active
      and current_user.role in CASE_WORKER_ROLES
      and current_user.office_id == office_id
    )

  @staticmethod
  def is_owner(appointment: Appointment, current_user: User) -> bool:
    """Return whether the authenticated citizen owns the appointment."""

    return (
      current_user.is_active
      and current_user.role == Role.CITIZEN
      and current_user.id == appointment.citizen_id
    )

  @staticmethod
  def can_view(appointment: Appointment, current_user: User) -> bool:
    """Return whether a user may see one appointment projection."""

    return AppointmentAccessPolicy.is_owner(
      appointment,
      current_user,
    ) or AppointmentAccessPolicy.can_manage_office(
      appointment.office_id,
      current_user,
    )

  @staticmethod
  def can_change_schedule(appointment: Appointment, current_user: User) -> bool:
    """Allow owners and responsible office case workers to change a schedule."""

    return AppointmentAccessPolicy.can_view(appointment, current_user)

  @staticmethod
  def can_record_outcome(appointment: Appointment, current_user: User) -> bool:
    """Allow only the responsible office to complete or mark a no-show."""

    return AppointmentAccessPolicy.can_manage_office(
      appointment.office_id,
      current_user,
    )
