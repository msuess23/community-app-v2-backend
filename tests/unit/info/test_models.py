from sqlalchemy import CheckConstraint

from src.info.models import Info, InfoImage, InfoStatusEntry


def test_info_model_is_mutable_crud_without_revision_or_soft_delete_columns() -> None:
  columns = set(Info.__table__.c.keys())

  assert {"id", "title", "current_status", "starts_at", "ends_at"} <= columns
  assert "version" not in columns
  assert "version_number" not in columns
  assert "is_current" not in columns
  assert "is_active" not in columns
  assert "archived_at" not in columns


def test_info_owns_one_address_and_statuses_cascade_on_delete() -> None:
  address_unique = next(
    constraint
    for constraint in Info.__table__.constraints
    if getattr(constraint, "columns", None)
    and {column.name for column in constraint.columns} == {"address_id"}
  )
  status_fk = next(iter(InfoStatusEntry.__table__.c.info_id.foreign_keys))

  assert address_unique is not None
  assert status_fk.ondelete == "CASCADE"
  assert Info.address.property.single_parent is True
  assert "delete-orphan" in Info.address.property.cascade
  assert "delete-orphan" in Info.status_entries.property.cascade


def test_info_database_constraints_cover_time_and_enum_values() -> None:
  names = {
    constraint.name
    for constraint in Info.__table__.constraints
    if isinstance(constraint, CheckConstraint)
  }
  status_names = {
    constraint.name
    for constraint in InfoStatusEntry.__table__.constraints
    if isinstance(constraint, CheckConstraint)
  }

  assert {
    "ck_infos_time_order",
    "ck_infos_category",
    "ck_infos_current_status",
  } <= names
  assert "ck_info_status_entries_status" in status_names


def test_info_images_are_current_crud_rows_with_cascade_delete() -> None:
  columns = set(InfoImage.__table__.c.keys())
  info_fk = next(iter(InfoImage.__table__.c.info_id.foreign_keys))
  index_names = {index.name for index in InfoImage.__table__.indexes}

  assert {
    "id",
    "info_id",
    "storage_key",
    "width",
    "height",
    "is_cover",
  } <= columns
  assert "is_active" not in columns
  assert "removed_at" not in columns
  assert "version" not in columns
  assert info_fk.ondelete == "CASCADE"
  assert "uq_info_images_cover" in index_names
  assert "delete-orphan" in Info.images.property.cascade
