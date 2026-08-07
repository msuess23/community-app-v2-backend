"""Add ordinary CRUD-owned images for public Infos.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-07-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
  """Create current Info image metadata with one optional cover per Info."""

  op.create_table(
    "info_images",
    sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("storage_key", sa.String(length=500), nullable=False),
    sa.Column("original_filename", sa.String(length=255), nullable=False),
    sa.Column("mime_type", sa.String(length=100), nullable=False),
    sa.Column("size_bytes", sa.BigInteger(), nullable=False),
    sa.Column("width", sa.Integer(), nullable=True),
    sa.Column("height", sa.Integer(), nullable=True),
    sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("is_cover", sa.Boolean(), nullable=False),
    sa.Column("info_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.CheckConstraint(
      "size_bytes > 0",
      name="ck_info_images_positive_size",
    ),
    sa.CheckConstraint(
      "width IS NULL OR width > 0",
      name="ck_info_images_positive_width",
    ),
    sa.CheckConstraint(
      "height IS NULL OR height > 0",
      name="ck_info_images_positive_height",
    ),
    sa.ForeignKeyConstraint(
      ["info_id"],
      ["infos.id"],
      ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("storage_key", name="uq_info_images_storage_key"),
  )
  op.create_index("ix_info_images_info_id", "info_images", ["info_id"])
  op.create_index(
    "ix_info_images_uploaded_by_user_id",
    "info_images",
    ["uploaded_by_user_id"],
  )
  op.create_index(
    "uq_info_images_cover",
    "info_images",
    ["info_id"],
    unique=True,
    postgresql_where=sa.text("is_cover"),
  )


def downgrade() -> None:
  """Remove current Info image metadata."""

  op.drop_index("uq_info_images_cover", table_name="info_images")
  op.drop_index(
    "ix_info_images_uploaded_by_user_id",
    table_name="info_images",
  )
  op.drop_index("ix_info_images_info_id", table_name="info_images")
  op.drop_table("info_images")
