from src.main import app


def test_ticket_openapi_keeps_old_filter_names_and_omits_office_from_create() -> None:
  schema = app.openapi()
  get_operation = schema["paths"]["/api/v1/tickets"]["get"]
  parameter_names = {parameter["name"] for parameter in get_operation["parameters"]}
  assert {"officeId", "createdFrom", "createdTo", "bbox", "sortBy"} <= parameter_names

  create_schema = schema["components"]["schemas"]["TicketCreateRequest"]
  assert "officeId" not in create_schema["properties"]
