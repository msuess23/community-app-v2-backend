"""Transaction-aware cleanup for files created or deleted by HTTP requests."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)

_ROLLBACK_FILES_KEY = "rollback_file_paths"
_COMMIT_DELETE_FILES_KEY = "commit_delete_file_paths"


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
  """Delete files staged by a transaction that could not commit."""

  paths = db.info.pop(_ROLLBACK_FILES_KEY, set())
  for path in paths:
    try:
      path.unlink(missing_ok=True)
    except OSError:
      # Cleanup is best-effort and must not hide the original transaction error.
      logger.warning(
        "Failed to delete transaction file during rollback cleanup: %s",
        path,
        exc_info=True,
      )


def register_commit_file_delete(db: AsyncSession, path: Path) -> None:
  """Delete an existing file only after its database row was committed away."""

  paths = db.info.setdefault(_COMMIT_DELETE_FILES_KEY, set())
  paths.add(path.resolve())


def clear_commit_file_deletes(db: AsyncSession) -> None:
  """Keep existing files when the surrounding database transaction rolls back."""

  db.info.pop(_COMMIT_DELETE_FILES_KEY, None)


def cleanup_commit_file_deletes(db: AsyncSession) -> None:
  """Best-effort removal of files whose database deletion has committed."""

  paths = db.info.pop(_COMMIT_DELETE_FILES_KEY, set())
  for path in paths:
    try:
      path.unlink(missing_ok=True)
    except OSError:
      # The database commit is already durable; leave an observable orphan.
      logger.warning(
        "Failed to delete transaction file after database commit: %s",
        path,
        exc_info=True,
      )
