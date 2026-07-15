from __future__ import annotations

import ast
from pathlib import Path

import src.address.models  # noqa: F401 - register metadata
import src.auth.models  # noqa: F401 - register metadata
import src.office.models  # noqa: F401 - register metadata
import src.user.models  # noqa: F401 - register metadata
from src.core.database import Base, NAMING_CONVENTION


VERSIONS_DIR = Path("alembic/versions")


def test_migrations_are_squashed_to_one_baseline() -> None:
  migrations = sorted(VERSIONS_DIR.glob("*.py"))
  assert [path.name for path in migrations] == [
    "c3e5f7a9b1d4_initial_schema.py"
  ]

  tree = ast.parse(migrations[0].read_text(encoding="utf-8"))
  assignments = {
    node.target.id: node.value
    for node in tree.body
    if isinstance(node, ast.AnnAssign)
    and isinstance(node.target, ast.Name)
  }
  down_revision = assignments["down_revision"]
  assert isinstance(down_revision, ast.Constant)
  assert down_revision.value is None


def test_baseline_contains_no_production_history_mechanisms() -> None:
  source = (VERSIONS_DIR / "c3e5f7a9b1d4_initial_schema.py").read_text(
    encoding="utf-8"
  )

  assert "CREATE TRIGGER" not in source
  assert "SYSTEM_USER" not in source
  assert "anonymized_at" not in source
  assert "anonymization_reason" not in source
  assert "uq_user_history_current_version" not in source
  assert "uq_office_history_current_version" not in source
  assert 'sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False)' in source


def test_historical_migrations_do_not_use_unnamed_foreign_keys() -> None:
  source = (VERSIONS_DIR / "c3e5f7a9b1d4_initial_schema.py").read_text(
    encoding="utf-8"
  )
  assert "create_foreign_key(None" not in source
  assert "drop_constraint(None" not in source


def test_metadata_has_deterministic_naming_convention() -> None:
  assert NAMING_CONVENTION == {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
  }

  unnamed = []
  for table in Base.metadata.tables.values():
    for constraint in table.constraints:
      if constraint.name is None:
        unnamed.append(f"{table.name}:{type(constraint).__name__}")

  assert unnamed == []
