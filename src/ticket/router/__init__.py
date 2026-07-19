"""Composes focused ticket routers without changing the public API paths."""

from fastapi import APIRouter

from src.ticket.router.community import router as community_router
from src.ticket.router.images import router as images_router
from src.ticket.router.public import router as public_router
from src.ticket.router.workflow import router as workflow_router

router = APIRouter()
# Register fixed internal search routes before the generic /{ticket_id} route.
for child_router in (
  workflow_router,
  public_router,
  community_router,
  images_router,
):
  router.routes.extend(child_router.routes)

__all__ = ["router"]
