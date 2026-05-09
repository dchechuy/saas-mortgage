"""nav_section unique name constraint + deduplicate

Revision ID: g7h8i9j0k1l2
Revises: f6514f92745d
Create Date: 2026-05-09

"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'f6514f92745d'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Delete duplicate nav_section rows — keep the lowest id per name
    conn.execute(sa.text("""
        DELETE FROM nav_section
        WHERE id NOT IN (
            SELECT MIN(id) FROM nav_section GROUP BY name
        )
    """))

    # 2. Add unique constraint
    op.create_unique_constraint('uq_nav_section_name', 'nav_section', ['name'])


def downgrade():
    op.drop_constraint('uq_nav_section_name', 'nav_section', type_='unique')
