from src.main import app


OPTIONAL_AUTH_OPERATIONS = (
  ("/api/v1/offices", "get"),
  ("/api/v1/offices/{office_id}", "get"),
  ("/api/v1/tickets", "get"),
  ("/api/v1/tickets/{ticket_id}", "get"),
  ("/api/v1/tickets/{ticket_id}/comments", "get"),
  ("/api/v1/tickets/{ticket_id}/images", "get"),
  ("/api/v1/tickets/{ticket_id}/images/{image_id}/content", "get"),
  ("/api/v1/offices/{office_id}/appointment-slots", "get"),
)


def test_optional_authentication_is_documented_as_anonymous_or_bearer():
  spec = app.openapi()

  for path, method in OPTIONAL_AUTH_OPERATIONS:
    assert spec["paths"][path][method]["security"] == [
      {},
      {"OAuth2PasswordBearer": []},
    ]


def test_required_authentication_remains_required_in_openapi():
  operation = app.openapi()["paths"]["/api/v1/tickets/internal"]["get"]

  assert operation["security"] == [{"OAuth2PasswordBearer": []}]
