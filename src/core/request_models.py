"""Shared Pydantic configuration for API request payloads."""

from pydantic import BaseModel, ConfigDict


class StrictRequestModel(BaseModel):
  """Reject unknown request fields instead of silently ignoring typos."""

  model_config = ConfigDict(extra="forbid")
