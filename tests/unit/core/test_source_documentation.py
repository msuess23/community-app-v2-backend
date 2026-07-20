"""Regression checks for source-level documentation coverage."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"
FIRST_PERSON_PATTERN = re.compile(r"\b(?:we|our|ours|us)\b", re.IGNORECASE)


def _documented_nodes() -> list[tuple[Path, ast.AST, str | None]]:
  """Collect every source class and function with its resolved docstring."""

  result: list[tuple[Path, ast.AST, str | None]] = []
  for path in sorted(SOURCE_ROOT.rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
      if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        result.append((path, node, ast.get_docstring(node)))
  return result


def test_every_source_class_and_function_has_a_docstring():
  """Require an explanatory docstring on every class, function, and method."""

  missing = [
    f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.name}"
    for path, node, docstring in _documented_nodes()
    if not docstring or not docstring.strip()
  ]
  assert missing == []


def test_source_docstrings_avoid_first_person_project_voice():
  """Keep docstrings descriptive instead of using first-person project voice."""

  violations = [
    f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.name}"
    for path, node, docstring in _documented_nodes()
    if docstring and FIRST_PERSON_PATTERN.search(docstring)
  ]
  assert violations == []


def _source_comments() -> list[tuple[Path, int, str]]:
  """Collect ordinary inline comments from every source module."""

  comments: list[tuple[Path, int, str]] = []
  for path in sorted(SOURCE_ROOT.rglob("*.py")):
    reader = io.StringIO(path.read_text(encoding="utf-8")).readline
    for token in tokenize.generate_tokens(reader):
      if token.type == tokenize.COMMENT:
        comments.append((path, token.start[0], token.string))
  return comments


def test_source_comments_avoid_first_person_project_voice():
  """Keep inline comments descriptive instead of using project voice."""

  violations = [
    f"{path.relative_to(PROJECT_ROOT)}:{line} {comment}"
    for path, line, comment in _source_comments()
    if FIRST_PERSON_PATTERN.search(comment)
  ]
  assert violations == []
