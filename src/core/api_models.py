"""Reusable Pydantic API conventions shared by client-facing domains."""

from pydantic import BaseModel, ConfigDict


def to_camel(value: str) -> str:
  """Converts a snake_case field name to lower camelCase."""

  head, *tail = value.split("_")
  return head + "".join(part.capitalize() for part in tail)


class CamelCaseApiModel(BaseModel):
  """Accepts Python field names while emitting client-friendly camelCase JSON."""

  model_config = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    from_attributes=True,
  )
