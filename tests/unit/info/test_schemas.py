from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.info.models import InfoCategory, InfoStatus
from src.info.schemas import (
  InfoCreateRequest,
  InfoStatusCreateRequest,
  InfoUpdateRequest,
)


def test_create_normalizes_text_and_retains_ktor_domain_values() -> None:
  starts_at = datetime.now(timezone.utc) + timedelta(days=1)
  request = InfoCreateRequest(
    title="  Neue   Baustelle  ",
    description="  Einschränkungen   im Verkehr  ",
    category=InfoCategory.CONSTRUCTION,
    starts_at=starts_at,
    ends_at=starts_at + timedelta(days=2),
  )

  assert request.title == "Neue Baustelle"
  assert request.description == "Einschränkungen im Verkehr"
  assert set(InfoCategory) == {
    InfoCategory.EVENT,
    InfoCategory.CONSTRUCTION,
    InfoCategory.MAINTENANCE,
    InfoCategory.ANNOUNCEMENT,
    InfoCategory.OTHER,
  }
  assert set(InfoStatus) == {
    InfoStatus.SCHEDULED,
    InfoStatus.ACTIVE,
    InfoStatus.DONE,
    InfoStatus.CANCELLED,
  }


@pytest.mark.parametrize(
  "payload",
  [
    {
      "title": "Invalid interval",
      "category": "EVENT",
      "starts_at": "2026-08-02T12:00:00+00:00",
      "ends_at": "2026-08-02T11:00:00+00:00",
    },
    {
      "title": "Naive interval",
      "category": "EVENT",
      "starts_at": "2026-08-02T12:00:00",
      "ends_at": "2026-08-02T13:00:00",
    },
  ],
)
def test_create_rejects_invalid_time_ranges(payload: dict) -> None:
  with pytest.raises(ValidationError):
    InfoCreateRequest.model_validate(payload)


def test_update_distinguishes_omitted_fields_from_explicit_null() -> None:
  request = InfoUpdateRequest(description=None, office_id=None, address=None)

  assert request.model_fields_set == {"description", "office_id", "address"}
  assert request.description is None
  assert request.office_id is None
  assert request.address is None

  with pytest.raises(ValidationError):
    InfoUpdateRequest(title=None)
  with pytest.raises(ValidationError):
    InfoUpdateRequest(category=None)
  with pytest.raises(ValidationError):
    InfoUpdateRequest(starts_at=None)


def test_requests_reject_unknown_fields_and_normalize_status_messages() -> None:
  with pytest.raises(ValidationError):
    InfoCreateRequest(
      title="Unknown field",
      category=InfoCategory.OTHER,
      starts_at="2026-08-02T12:00:00+00:00",
      ends_at="2026-08-02T13:00:00+00:00",
      legacy_field=True,
    )

  request = InfoStatusCreateRequest(
    status=InfoStatus.ACTIVE,
    message="  Work   started  ",
  )
  assert request.message == "Work started"
