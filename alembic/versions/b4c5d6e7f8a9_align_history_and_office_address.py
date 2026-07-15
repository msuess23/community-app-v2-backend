"""Align snapshot history and office-owned address lifecycle.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  # The lifecycle timestamp belongs to the live user. In a history snapshot,
  # changed_at already identifies when the inactive state became valid.
  op.drop_column("user_history", "deactivated_at")

  # Office owns its address record. Addresses themselves remain independent and
  # have no relationship back to an office, but one address row must not be
  # shared by multiple offices.
  op.create_unique_constraint(
    "uq_offices_address_id",
    "offices",
    ["address_id"],
  )


def downgrade() -> None:
  op.drop_constraint("uq_offices_address_id", "offices", type_="unique")
  op.add_column(
    "user_history",
    sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
  )
