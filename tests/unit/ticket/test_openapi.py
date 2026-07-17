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
