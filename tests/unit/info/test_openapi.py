from src.main import app


def test_info_crud_and_status_routes_are_documented() -> None:
  paths = app.openapi()["paths"]

  assert set(paths["/api/v1/infos"]) == {"get", "post"}
  assert set(paths["/api/v1/infos/{info_id}"]) == {"get", "put", "delete"}
  assert set(paths["/api/v1/infos/{info_id}/status"]) == {"get", "put"}
  assert set(paths["/api/v1/infos/{info_id}/status/current"]) == {"get"}

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
