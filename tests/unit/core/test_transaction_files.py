from pathlib import Path
from unittest.mock import MagicMock

from src.core.transaction_files import (
  cleanup_commit_file_deletes,
  cleanup_rollback_files,
  register_commit_file_delete,
  register_rollback_file,
)


def _db():
  db = MagicMock()
  db.info = {}
  return db


def test_rollback_cleanup_logs_file_system_errors(monkeypatch, tmp_path, caplog):
  db = _db()
  target = tmp_path / "rollback.bin"
  register_rollback_file(db, target)

  def fail_unlink(self, *, missing_ok=False):
    del missing_ok
    if self == target.resolve():
      raise OSError("permission denied")

  monkeypatch.setattr(Path, "unlink", fail_unlink)

  cleanup_rollback_files(db)

  assert "rollback cleanup" in caplog.text
  assert str(target.resolve()) in caplog.text


def test_post_commit_cleanup_logs_file_system_errors(monkeypatch, tmp_path, caplog):
  db = _db()
  target = tmp_path / "committed.bin"
  register_commit_file_delete(db, target)

  def fail_unlink(self, *, missing_ok=False):
    del missing_ok
    if self == target.resolve():
      raise OSError("permission denied")

  monkeypatch.setattr(Path, "unlink", fail_unlink)

  cleanup_commit_file_deletes(db)

  assert "after database commit" in caplog.text
  assert str(target.resolve()) in caplog.text
