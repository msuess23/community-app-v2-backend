"""Rollback cleanup for files written before an HTTP transaction commits."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession


_ROLLBACK_FILES_KEY = "rollback_file_paths"


def register_rollback_file(db: AsyncSession, path: Path) -> None:
  """Register a newly written file for deletion when the transaction rolls back."""

  paths = db.info.setdefault(_ROLLBACK_FILES_KEY, set())
  paths.add(path.resolve())


def unregister_rollback_file(db: AsyncSession, path: Path) -> None:
  """Remove a file from rollback tracking after explicit early cleanup."""

  paths = db.info.get(_ROLLBACK_FILES_KEY)
  if paths is None:
    return
  paths.discard(path.resolve())
  if not paths:
    db.info.pop(_ROLLBACK_FILES_KEY, None)


def clear_rollback_files(db: AsyncSession) -> None:
  """Forget rollback candidates after a successful database commit."""

  db.info.pop(_ROLLBACK_FILES_KEY, None)


def cleanup_rollback_files(db: AsyncSession) -> None:
  """Delete all files staged by a transaction that could not commit."""

  paths = db.info.pop(_ROLLBACK_FILES_KEY, set())
  for path in paths:
    try:
      path.unlink(missing_ok=True)
    except OSError:
      # Cleanup is best-effort and must not hide the original transaction error.
      continue
