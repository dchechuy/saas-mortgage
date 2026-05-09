"""Deduplicate nav_item rows and add unique constraint on (section_id, page_slug)

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-05-09

"""
from alembic import op
import sqlalchemy as sa

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Keep only the lowest-id nav_item per (section_id, page_slug)
    conn.execute(sa.text("""
        DELETE FROM nav_item
        WHERE id NOT IN (
            SELECT MIN(id) FROM nav_item GROUP BY section_id, page_slug
        )
    """))

    with op.batch_alter_table('nav_item') as batch_op:
        batch_op.create_unique_constraint('uq_nav_item_section_slug', ['section_id', 'page_slug'])


def downgrade():
    with op.batch_alter_table('nav_item') as batch_op:
        batch_op.drop_constraint('uq_nav_item_section_slug', type_='unique')
