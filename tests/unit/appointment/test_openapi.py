"""OpenAPI coverage for the first appointment API increment."""

from src.main import app


def test_appointment_patch_one_routes_are_documented() -> None:
  paths = app.openapi()["paths"]

  assert "/api/v1/offices/{office_id}/appointment-slots" in paths
  assert "/api/v1/offices/{office_id}/appointment-slots/{slot_id}" in paths
  assert "/api/v1/appointment-slots/{slot_id}/book" in paths
  assert "/api/v1/appointments/mine" in paths
  assert "/api/v1/appointments/internal" in paths
  assert "/api/v1/appointments/{appointment_id}" in paths
