from src.main import app


def test_ticket_openapi_exposes_public_and_workflow_endpoints() -> None:
  paths = app.openapi()["paths"]

  assert "/api/v1/tickets" in paths
  assert "/api/v1/tickets/mine" in paths
  assert "/api/v1/tickets/work-queue" in paths
  assert "/api/v1/tickets/{ticket_id}/internal" in paths
  assert "/api/v1/tickets/{ticket_id}/events" in paths
  assert "/api/v1/tickets/{ticket_id}/workflow" in paths
  assert "/api/v1/tickets/{ticket_id}/allowed-actions" not in paths


def test_ticket_openapi_exposes_comments_and_revisioned_images_without_votes() -> None:
  paths = app.openapi()["paths"]

  assert "/api/v1/tickets/{ticket_id}/comments" in paths
  assert "/api/v1/tickets/{ticket_id}/images" in paths
  assert "/api/v1/tickets/{ticket_id}/images/{image_id}/cover" in paths
  assert "/api/v1/tickets/{ticket_id}/vote" not in paths


def test_ticket_openapi_uses_snake_case_contract() -> None:
  spec = app.openapi()
  public_parameters = {
    parameter["name"]
    for parameter in spec["paths"]["/api/v1/tickets"]["get"]["parameters"]
  }
  queue_parameters = {
    parameter["name"]
    for parameter in spec["paths"]["/api/v1/tickets/work-queue"]["get"]["parameters"]
  }
  ticket_fields = set(
    spec["components"]["schemas"]["TicketResponse"]["properties"]
  )
  cosignature_fields = set(
    spec["components"]["schemas"]["RequestCosignatureAction"]["properties"]
  )

  assert {"office_id", "created_from", "created_to", "sort_by"} <= public_parameters
  assert {"workflow_state", "sort_by"} <= queue_parameters
  assert {"current_status", "image_url"} <= ticket_fields
  assert "creator_user_id" not in ticket_fields
  internal_fields = set(
    spec["components"]["schemas"]["TicketInternalResponse"]["properties"]
  )
  assert "creator_user_id" in internal_fields
  assert "target_user_id" in cosignature_fields
  assert "targetUserId" not in cosignature_fields


def test_public_ticket_schemas_do_not_expose_internal_user_ids() -> None:
  schemas = app.openapi()["components"]["schemas"]

  assert "creator_user_id" not in schemas["TicketResponse"]["properties"]
  assert "created_by_user_id" not in schemas["TicketStatusResponse"]["properties"]
  assert "author_user_id" not in schemas["TicketCommentResponse"]["properties"]
  image_fields = schemas["TicketImageResponse"]["properties"]
  assert "uploaded_by_user_id" not in image_fields
  assert {"width", "height", "is_cover"} <= image_fields.keys()
  assert "creator_user_id" in schemas["TicketInternalResponse"]["properties"]


def test_histories_and_ticket_events_use_common_page_contract() -> None:
  spec = app.openapi()

  for path in (
    "/api/v1/users/{user_id}/history",
    "/api/v1/offices/{office_id}/history",
    "/api/v1/tickets/{ticket_id}/events",
  ):
    operation = spec["paths"][path]["get"]
    parameter_names = {parameter["name"] for parameter in operation["parameters"]}
    response_schema = operation["responses"]["200"]["content"][
      "application/json"
    ]["schema"]

    assert {"page", "size"} <= parameter_names
    assert response_schema["$ref"].split("/")[-1].startswith("PaginatedResponse_")
