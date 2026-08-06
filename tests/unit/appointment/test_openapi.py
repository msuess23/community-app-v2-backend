"""OpenAPI coverage for the appointment lifecycle API."""

from src.main import app


def test_appointment_patch_one_routes_are_documented() -> None:
  paths = app.openapi()["paths"]

  assert "/api/v1/offices/{office_id}/appointment-slots" in paths
  assert "/api/v1/offices/{office_id}/appointment-slots/{slot_id}" in paths
  assert "/api/v1/appointment-slots/{slot_id}/book" in paths
  assert "/api/v1/appointments/mine" in paths
  assert "/api/v1/appointments/internal" in paths
  assert "/api/v1/appointments/{appointment_id}" in paths
  assert "/api/v1/appointments/{appointment_id}/reschedule" in paths
  assert "/api/v1/appointments/{appointment_id}/cancel" in paths
  assert "/api/v1/appointments/{appointment_id}/complete" in paths
  assert "/api/v1/appointments/{appointment_id}/no-show" in paths
  assert "/api/v1/appointments/{appointment_id}/events" in paths
  assert "/api/v1/appointments/{appointment_id}/documents" in paths
  assert (
    "/api/v1/appointments/{appointment_id}/documents/"
    "{document_group_id}/versions"
  ) in paths
  assert (
    "/api/v1/appointments/{appointment_id}/documents/"
    "{document_version_id}/content"
  ) in paths


def test_appointment_contract_exposes_references_filters_and_binary_pdf() -> None:
  schema = app.openapi()
  paths = schema["paths"]
  schemas = schema["components"]["schemas"]

  assert "/api/v1/appointments/internal/filter-options" in paths
  assert "AppointmentFilterOptionsResponse" in schemas
  assert "AppointmentOfficeReference" in schemas
  assert "AppointmentUserReference" in schemas
  assert "AppointmentTicketReference" in schemas

  appointment_properties = schemas["AppointmentResponse"]["properties"]
  assert "office" in appointment_properties
  assert "citizen" in appointment_properties
  assert "ticket" in appointment_properties

  event_properties = schemas["AppointmentEventResponse"]["properties"]
  assert "actor" in event_properties

  content_path = (
    paths[
      "/api/v1/appointments/{appointment_id}/documents/"
      "{document_version_id}/content"
    ]["get"]["responses"]["200"]["content"]
  )
  assert "application/pdf" in content_path
  assert content_path["application/pdf"]["schema"] == {
    "type": "string",
    "format": "binary",
  }
