"""OpenAPI helpers for runtime semantics FastAPI cannot infer automatically."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import FastAPI

try:
  # FastAPI 0.139 and newer keep included routers as lazy route containers.
  from fastapi.routing import iter_route_contexts
except ImportError:
  # Older FastAPI versions expose included APIRoutes directly in app.routes.
  iter_route_contexts = None


def _depends_on(
  dependant: Any,
  dependency: Callable[..., Any],
) -> bool:
  """Return whether a FastAPI dependency tree contains a target callable."""

  if dependant.call is dependency:
    return True

  return any(
    _depends_on(child, dependency)
    for child in dependant.dependencies
  )


def _iter_api_routes(app: FastAPI) -> Iterator[Any]:
  """Yield effective API routes across supported FastAPI router layouts."""

  candidates = (
    iter_route_contexts(app.routes)
    if iter_route_contexts is not None
    else app.routes
  )

  for route in candidates:
    # Starlette documentation routes and mounts do not expose a Dependant.
    if getattr(route, "dependant", None) is None:
      continue

    if not getattr(route, "methods", None):
      continue

    if not getattr(route, "include_in_schema", False):
      continue

    yield route


def install_optional_auth_openapi(
  app: FastAPI,
  *,
  optional_user_dependency: Callable[..., Any],
  security_scheme_name: str,
) -> None:
  """Document endpoints that accept anonymous or bearer-authenticated access."""

  original_openapi = app.openapi

  def custom_openapi() -> dict[str, Any]:
    """Generate OpenAPI and apply optional-auth security alternatives."""

    schema = original_openapi()

    for route in _iter_api_routes(app):
      if not _depends_on(route.dependant, optional_user_dependency):
        continue

      # path_format contains the fully prefixed path used as the OpenAPI key.
      route_path = (
        getattr(route, "path_format", None)
        or getattr(route, "path", None)
      )
      if route_path is None:
        continue

      path_item = schema["paths"].get(route_path, {})

      for method in route.methods or set():
        operation = path_item.get(method.lower())
        if operation is None:
          continue

        operation["security"] = [
          {},
          {security_scheme_name: []},
        ]

    app.openapi_schema = schema
    return schema

  app.openapi = custom_openapi

  # Discard schemas generated before this hook was installed.
  app.openapi_schema = None