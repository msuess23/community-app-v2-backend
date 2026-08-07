"""Add reusable image dimensions to ticket media projections.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
  """Add optional dimensions for existing and future ticket images."""

  op.add_column("ticket_images", sa.Column("width", sa.Integer(), nullable=True))
  op.add_column("ticket_images", sa.Column("height", sa.Integer(), nullable=True))
  op.create_check_constraint(
    "ck_ticket_images_positive_width",
    "ticket_images",
    "width IS NULL OR width > 0",
  )
  op.create_check_constraint(
    "ck_ticket_images_positive_height",
    "ticket_images",
    "height IS NULL OR height > 0",
  )


def downgrade() -> None:
  """Remove image dimensions while preserving all prior metadata."""

  op.drop_constraint(
    "ck_ticket_images_positive_height",
    "ticket_images",
    type_="check",
  )
  op.drop_constraint(
    "ck_ticket_images_positive_width",
    "ticket_images",
    type_="check",
  )
  op.drop_column("ticket_images", "height")
  op.drop_column("ticket_images", "width")
