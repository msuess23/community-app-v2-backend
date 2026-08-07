import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert, select

from src.core.exceptions import DomainValidationException
from src.core.filters import apply_search_filter, escape_like_pattern, get_bbox_filter


def test_search_wildcards_are_escaped():
  assert escape_like_pattern("50%_off\\today") == r"50\%\_off\\today"


def test_search_terms_can_match_across_multiple_columns():
  metadata = MetaData()
  users = Table(
    "search_test_users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, nullable=False),
    Column("first_name", String, nullable=False),
    Column("last_name", String, nullable=False),
  )
  engine = create_engine("sqlite://")
  metadata.create_all(engine)

  with engine.begin() as connection:
    connection.execute(
      insert(users),
      [
        {
          "id": 1,
          "email": "carla@example.test",
          "first_name": "Carla",
          "last_name": "Citizen",
        },
        {
          "id": 2,
          "email": "carla@example.test",
          "first_name": "Carla",
          "last_name": "Officer",
        },
      ],
    )
    query = apply_search_filter(
      select(users.c.id),
      "Carla Citizen",
      users.c.email,
      users.c.first_name,
      users.c.last_name,
    )
    result = connection.execute(query).scalars().all()

  assert result == [1]


def test_search_requires_every_term_but_not_the_same_column():
  metadata = MetaData()
  records = Table(
    "search_test_records",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String, nullable=False),
    Column("description", String, nullable=False),
  )
  engine = create_engine("sqlite://")
  metadata.create_all(engine)

  with engine.begin() as connection:
    connection.execute(
      insert(records),
      [
        {"id": 1, "title": "Defekte Straße", "description": "Großes Schlagloch"},
        {"id": 2, "title": "Defekte Straße", "description": "Laterne ausgefallen"},
      ],
    )
    query = apply_search_filter(
      select(records.c.id),
      "Straße Schlagloch",
      records.c.title,
      records.c.description,
    )
    result = connection.execute(query).scalars().all()

  assert result == [1]


@pytest.mark.parametrize(
  "bbox",
  [
    "-181,0,1,1",
    "0,-91,1,1",
    "10,0,5,1",
    "0,10,1,5",
    "0,0,1",
  ],
)
def test_invalid_bbox_is_rejected(bbox: str):
  with pytest.raises(DomainValidationException) as exc_info:
    get_bbox_filter(bbox)

  assert exc_info.value.error_code == "INVALID_BOUNDING_BOX"


def test_valid_bbox_is_parsed():
  assert get_bbox_filter("10,20,30,40") == (10.0, 20.0, 30.0, 40.0)
