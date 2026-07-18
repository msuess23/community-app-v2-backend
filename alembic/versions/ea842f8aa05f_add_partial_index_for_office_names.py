"""add_partial_index_for_office_names

Revision ID: ea842f8aa05f
Revises: fb3008404a5a
Create Date: 2026-07-09 01:17:31.888007

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ea842f8aa05f'
down_revision: Union[str, Sequence[str], None] = 'fb3008404a5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_constraint(op.f('offices_name_key'), 'offices', type_='unique')
    
    op.execute("""
        CREATE UNIQUE INDEX idx_unique_active_office_name 
        ON offices (name) 
        WHERE is_active = True;
    """)


def downgrade():
    op.execute("DROP INDEX idx_unique_active_office_name;")
    op.create_unique_constraint('offices_name_key', 'offices', ['name'])
