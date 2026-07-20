"""OpenAPI helpers for runtime semantics FastAPI cannot infer automatically."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute


def _depends_on(dependant: Any, dependency: Callable[..., Any]) -> bool:
  """Return whether a FastAPI dependency tree contains a target callable."""

  if dependant.call is dependency:
    return True
  return any(
    _depends_on(child, dependency)
    for child in dependant.dependencies
  )


def install_optional_auth_openapi(
  app: FastAPI,
  *,
  optional_user_dependency: Callable[..., Any],
  security_scheme_name: str,
) -> None:
  """Document endpoints that accept either anonymous or bearer-auth access."""

  def custom_openapi() -> dict[str, Any]:
    """Generate and cache OpenAPI with optional bearer-auth alternatives."""

    if app.openapi_schema is not None:
      return app.openapi_schema

    schema = get_openapi(
      title=app.title,
      version=app.version,
      openapi_version=app.openapi_version,
      summary=app.summary,
      description=app.description,
      routes=app.routes,
      tags=app.openapi_tags,
      servers=app.servers,
      terms_of_service=app.terms_of_service,
      contact=app.contact,
      license_info=app.license_info,
      separate_input_output_schemas=app.separate_input_output_schemas,
    )

    for route in app.routes:
      if not isinstance(route, APIRoute):
        continue
      if not _depends_on(route.dependant, optional_user_dependency):
        continue

      path_item = schema["paths"].get(route.path, {})
      for method in route.methods or set():
        operation = path_item.get(method.lower())
        if operation is not None:
          operation["security"] = [
            {},
            {security_scheme_name: []},
          ]

    app.openapi_schema = schema
    return schema

  app.openapi = custom_openapi
