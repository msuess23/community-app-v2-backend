
import pytest
from pydantic import BaseModel, Field, ValidationError

from src.core.validation import (
  NonNullableNormalizedUpdateText,
  NormalizedOptionalText,
  NormalizedRequiredText,
)


class NormalizedTextModel(BaseModel):
  required: NormalizedRequiredText = Field(..., min_length=3)
  optional: NormalizedOptionalText = Field(None, max_length=20)
  patch_value: NonNullableNormalizedUpdateText = Field(None, min_length=2)


def test_common_text_types_normalize_before_length_validation() -> None:
  model = NormalizedTextModel(
    required="  three   words ",
    optional="  optional   value ",
  )
  assert model.required == "three words"
  assert model.optional == "optional value"

  with pytest.raises(ValidationError):
    NormalizedTextModel(required="   ab   ")


def test_optional_and_non_nullable_patch_text_have_distinct_null_semantics() -> None:
  assert NormalizedTextModel(required="valid", optional="   ").optional is None
  with pytest.raises(ValidationError):
    NormalizedTextModel(required="valid", patch_value=None)
