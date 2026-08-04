from src.main import app


def _request_body_schema(spec: dict, path: str) -> dict:
  schema = spec["paths"][path]["post"]["requestBody"]["content"][
    "multipart/form-data"
  ]["schema"]
  if "$ref" in schema:
    return spec["components"]["schemas"][schema["$ref"].split("/")[-1]]
  return schema


def test_info_crud_and_status_routes_are_documented() -> None:
  paths = app.openapi()["paths"]

  assert set(paths["/api/v1/infos"]) == {"get", "post"}
  assert set(paths["/api/v1/infos/{info_id}"]) == {"get", "put", "delete"}
  assert set(paths["/api/v1/infos/{info_id}/status"]) == {"get", "put"}
  assert set(paths["/api/v1/infos/{info_id}/status/current"]) == {"get"}
  assert set(paths["/api/v1/infos/{info_id}/images"]) == {"get", "post"}
  assert set(paths["/api/v1/infos/{info_id}/images/{image_id}"]) == {"delete"}
  assert set(
    paths["/api/v1/infos/{info_id}/images/{image_id}/cover"]
  ) == {"put"}
  assert set(
    paths["/api/v1/infos/{info_id}/images/{image_id}/content"]
  ) == {"get"}

  assert "/api/info" not in paths
  assert not any(path.startswith("/api/media") for path in paths)
  assert "/api/v1/infos/{info_id}/versions" not in paths


def test_info_contract_uses_new_snake_case_helpers() -> None:
  spec = app.openapi()
  parameters = {
    parameter["name"]
    for parameter in spec["paths"]["/api/v1/infos"]["get"]["parameters"]
  }
  response_fields = set(spec["components"]["schemas"]["InfoResponse"]["properties"])

  assert {
    "office_id",
    "starts_from",
    "ends_to",
    "status",
    "bbox",
    "q",
    "page",
    "size",
    "sort_by",
    "order",
  } <= parameters
  assert {
    "current_status",
    "image_url",
    "starts_at",
    "ends_at",
  } <= response_fields
  assert "officeId" not in parameters
  assert "created_by_user_id" not in spec["components"]["schemas"][
    "InfoStatusResponse"
  ]["properties"]


def test_info_is_classical_crud_without_revision_schemas() -> None:
  schemas = app.openapi()["components"]["schemas"]
  info_fields = schemas["InfoResponse"]["properties"]

  assert "version" not in info_fields
  assert "is_current" not in info_fields
  assert "archived_at" not in info_fields
  assert "InfoVersionResponse" not in schemas


def test_info_image_contract_reuses_current_media_metadata_without_revisions() -> None:
  spec = app.openapi()
  schemas = spec["components"]["schemas"]
  fields = schemas["InfoImageResponse"]["properties"]

  assert {
    "id",
    "info_id",
    "url",
    "original_filename",
    "mime_type",
    "size_bytes",
    "width",
    "height",
    "alt_text",
    "uploaded_at",
    "is_cover",
  } <= set(fields)
  assert "is_active" not in fields
  assert "removed_at" not in fields
  assert "version" not in fields
  upload = _request_body_schema(spec, "/api/v1/infos/{info_id}/images")
  assert {"file", "alt_text"} <= set(upload["required"])
  assert upload["properties"]["alt_text"]["minLength"] == 1
  assert upload["properties"]["alt_text"]["maxLength"] == 500

  ticket_upload = _request_body_schema(
    spec,
    "/api/v1/tickets/{ticket_id}/images",
  )
  assert "alt_text" not in ticket_upload["properties"]
  assert "alt_text" not in schemas["TicketImageResponse"]["properties"]
  assert not any(path.startswith("/api/media") for path in spec["paths"])
