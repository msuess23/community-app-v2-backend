"""Require accessible alternative text for Info images.

Revision ID: e8f9a0b1c2d3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
  """Add mandatory normalized alternative text to current Info images."""

  op.add_column(
    "info_images",
    sa.Column("alt_text", sa.String(length=500), nullable=True),
  )
  # Legacy rows predate accessible upload metadata. Their filename is retained
  # as a deterministic migration fallback; all new uploads require authored text.
  op.execute(
    "UPDATE info_images SET alt_text = original_filename WHERE alt_text IS NULL"
  )
  op.alter_column("info_images", "alt_text", nullable=False)
  op.create_check_constraint(
    "ck_info_images_alt_text_not_blank",
    "info_images",
    "length(btrim(alt_text)) > 0",
  )


def downgrade() -> None:
  """Remove Info-specific alternative text without touching ticket images."""

  op.drop_constraint(
    "ck_info_images_alt_text_not_blank",
    "info_images",
    type_="check",
  )
  op.drop_column("info_images", "alt_text")
