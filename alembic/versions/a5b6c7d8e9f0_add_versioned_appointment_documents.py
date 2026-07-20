"""Add immutable versioned PDF documents for appointments.

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DOCUMENT_TYPES = ("CONFIRMATION", "FORM", "NOTICE", "PROTOCOL", "OTHER")


def _check(column: str, values: tuple[str, ...]) -> str:
  return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
  """Create document groups whose immutable versions belong to appointments."""

  op.create_table(
    "appointment_documents",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("document_group_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("version_number", sa.Integer(), nullable=False),
    sa.Column("document_type", sa.String(length=32), nullable=False),
    sa.Column("storage_key", sa.String(length=500), nullable=False),
    sa.Column("original_filename", sa.String(length=255), nullable=False),
    sa.Column("mime_type", sa.String(length=100), nullable=False),
    sa.Column("size_bytes", sa.BigInteger(), nullable=False),
    sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("is_current", sa.Boolean(), nullable=False),
    sa.Column("visible_to_citizen", sa.Boolean(), nullable=False),
    sa.Column("replaced_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.CheckConstraint(
      "version_number >= 1",
      name="ck_appointment_documents_version_positive",
    ),
    sa.CheckConstraint(
      "size_bytes > 0",
      name="ck_appointment_documents_size_positive",
    ),
    sa.CheckConstraint(
      _check("document_type", _DOCUMENT_TYPES),
      name="ck_appointment_documents_type",
    ),
    sa.ForeignKeyConstraint(
      ["appointment_id"],
      ["appointments.id"],
      ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(
      ["replaced_version_id"],
      ["appointment_documents.id"],
    ),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint(
      "document_group_id",
      "version_number",
      name="uq_appointment_documents_group_version",
    ),
    sa.UniqueConstraint("storage_key", name="uq_appointment_documents_storage_key"),
  )
  op.create_index(
    "ix_appointment_documents_appointment_id",
    "appointment_documents",
    ["appointment_id"],
  )
  op.create_index(
    "ix_appointment_documents_document_group_id",
    "appointment_documents",
    ["document_group_id"],
  )
  op.create_index(
    "ix_appointment_documents_is_current",
    "appointment_documents",
    ["is_current"],
  )
  op.create_index(
    "ix_appointment_documents_uploaded_by_user_id",
    "appointment_documents",
    ["uploaded_by_user_id"],
  )
  op.create_index(
    "uq_appointment_documents_current_group",
    "appointment_documents",
    ["document_group_id"],
    unique=True,
    postgresql_where=sa.text("is_current"),
  )


def downgrade() -> None:
  """Remove versioned appointment document metadata."""

  op.drop_index(
    "uq_appointment_documents_current_group",
    table_name="appointment_documents",
  )
  op.drop_index(
    "ix_appointment_documents_uploaded_by_user_id",
    table_name="appointment_documents",
  )
  op.drop_index(
    "ix_appointment_documents_is_current",
    table_name="appointment_documents",
  )
  op.drop_index(
    "ix_appointment_documents_document_group_id",
    table_name="appointment_documents",
  )
  op.drop_index(
    "ix_appointment_documents_appointment_id",
    table_name="appointment_documents",
  )
  op.drop_table("appointment_documents")
