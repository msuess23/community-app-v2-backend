from src.main import app


def test_ticket_openapi_keeps_old_filter_names_and_omits_office_from_create() -> None:
  schema = app.openapi()
  get_operation = schema["paths"]["/api/v1/tickets"]["get"]
  parameter_names = {parameter["name"] for parameter in get_operation["parameters"]}
  assert {"officeId", "createdFrom", "createdTo", "bbox", "sortBy"} <= parameter_names

  create_schema = schema["components"]["schemas"]["TicketCreateRequest"]
  assert "officeId" not in create_schema["properties"]


def test_ticket_openapi_exposes_authority_workflow_endpoints() -> None:
  schema = app.openapi()
  paths = schema["paths"]

  assert "/api/v1/tickets/work-queue" in paths
  assert "/api/v1/tickets/{ticket_id}/internal" in paths
  assert "/api/v1/tickets/{ticket_id}/events" in paths
  assert "/api/v1/tickets/{ticket_id}/allowed-actions" in paths
  assert "/api/v1/tickets/{ticket_id}/dispatch" in paths
  assert "/api/v1/tickets/{ticket_id}/primary-officer" in paths
  assert "/api/v1/tickets/{ticket_id}/workflow" in paths


def test_ticket_openapi_exposes_vote_and_revisioned_image_endpoints() -> None:
  schema = app.openapi()
  paths = schema["paths"]

  assert "/api/v1/tickets/{ticket_id}/vote" in paths
  assert "/api/v1/tickets/{ticket_id}/images" in paths
  assert "/api/v1/tickets/{ticket_id}/images/{image_id}/cover" in paths
  assert "/api/v1/tickets/{ticket_id}/images/{image_id}/content" in paths
