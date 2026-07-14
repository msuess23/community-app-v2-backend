from __future__ import annotations

import ast
from pathlib import Path


ALLOWED_TRANSACTION_FILES = {
  Path("src/core/database.py"),
}


def test_services_and_repositories_do_not_commit_or_rollback():
  violations: list[str] = []

  for path in Path("src").rglob("*.py"):
    if path in ALLOWED_TRANSACTION_FILES:
      continue

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
      if not isinstance(node, ast.Call):
        continue
      function = node.func
      if not isinstance(function, ast.Attribute):
        continue
      if function.attr in {"commit", "rollback"}:
        violations.append(f"{path}:{node.lineno}:{function.attr}")

  assert violations == []
