from __future__ import annotations

import uuid
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


REQUEST_ID_HEADER = "X-Request-ID"


def _resolve_request_id(scope: Scope) -> str:
  """Accept UUID request IDs only; generate a safe value for all other input."""
  raw_value = Headers(scope=scope).get(REQUEST_ID_HEADER)
  if raw_value:
    try:
      return str(uuid.UUID(raw_value))
    except (ValueError, AttributeError):
      pass
  return str(uuid.uuid4())


class RequestIdMiddleware:
  """Attach a correlation ID to every HTTP request and response."""

  def __init__(self, app: ASGIApp) -> None:
    self.app = app

  async def __call__(
    self,
    scope: Scope,
    receive: Receive,
    send: Send,
  ) -> None:
    if scope["type"] != "http":
      await self.app(scope, receive, send)
      return

    request_id = _resolve_request_id(scope)
    scope.setdefault("state", {})["request_id"] = request_id

    async def send_with_request_id(message: Message) -> None:
      if message["type"] == "http.response.start":
        MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
      await send(message)

    await self.app(scope, receive, send_with_request_id)
