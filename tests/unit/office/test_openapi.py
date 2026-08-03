from src.main import app


def test_office_history_openapi_uses_typed_opening_hours() -> None:
  schemas = app.openapi()["components"]["schemas"]
  opening_hours_schema = schemas["OfficeHistoryResponse"]["properties"][
    "opening_hours"
  ]

  assert opening_hours_schema["$ref"] == "#/components/schemas/OpeningHours"


def test_office_openapi_describes_result_state_snapshots() -> None:
  paths = app.openapi()["paths"]

  update_description = paths["/api/v1/offices/{office_id}"]["patch"][
    "description"
  ]
  history_description = paths["/api/v1/offices/{office_id}/history"]["get"][
    "description"
  ]

  assert "resulting state snapshot" in update_description
  assert "result-state snapshots" in history_description
