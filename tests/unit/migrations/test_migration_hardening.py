from __future__ import annotations

import ast
from pathlib import Path

import src.address.models  # noqa: F401 - register metadata
import src.auth.models  # noqa: F401 - register metadata
import src.office.models  # noqa: F401 - register metadata
import src.user.models  # noqa: F401 - register metadata
from src.core.database import Base, NAMING_CONVENTION


VERSIONS_DIR = Path("alembic/versions")


def _function_has_effect(function: ast.FunctionDef) -> bool:
  meaningful = [
    node
    for node in function.body
    if not (
      isinstance(node, ast.Expr)
      and isinstance(node.value, ast.Constant)
      and isinstance(node.value.value, str)
    )
  ]
  return not (len(meaningful) == 1 and isinstance(meaningful[0], ast.Pass))


def test_migration_chain_contains_no_noop_revisions() -> None:
  noops: list[str] = []
  for path in VERSIONS_DIR.glob("*.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = {
      node.name: node
      for node in tree.body
      if isinstance(node, ast.FunctionDef) and node.name in {"upgrade", "downgrade"}
    }
    if functions and not any(_function_has_effect(fn) for fn in functions.values()):
      noops.append(path.name)

  assert noops == []


def test_historical_migrations_do_not_use_unnamed_foreign_keys() -> None:
  violations: list[str] = []
  for path in VERSIONS_DIR.glob("*.py"):
    source = path.read_text(encoding="utf-8")
    if "create_foreign_key(None" in source or "drop_constraint(None" in source:
      violations.append(path.name)

  assert violations == []


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


def test_broken_office_index_downgrade_was_repaired() -> None:
  source = (
    VERSIONS_DIR / "65ec6cbfc19c_remove_partial_index_for_office_name.py"
  ).read_text(encoding="utf-8")
  downgrade_source = source.split("def downgrade", maxsplit=1)[1]

  assert "idx_unique_active_office_name" in downgrade_source
  assert "create_unique_constraint" not in downgrade_source


def test_history_guard_migration_protects_update_delete_and_truncate() -> None:
  source = (
    VERSIONS_DIR / "a1c3e5f7b9d2_database_history_hardening.py"
  ).read_text(encoding="utf-8")

  assert "BEFORE UPDATE OR DELETE ON user_history" in source
  assert "BEFORE UPDATE OR DELETE ON office_history" in source
  assert "BEFORE TRUNCATE ON user_history" in source
  assert "BEFORE TRUNCATE ON office_history" in source
  assert "retention period has not expired" in source
