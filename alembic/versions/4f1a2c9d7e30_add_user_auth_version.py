"""add user auth version

Revision ID: 4f1a2c9d7e30
Revises: 65ec6cbfc19c
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4f1a2c9d7e30"
down_revision: Union[str, Sequence[str], None] = "65ec6cbfc19c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_version")
