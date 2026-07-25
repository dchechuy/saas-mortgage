"""add tenant_management nav item

Revision ID: e0ff5103a60e
Revises: 7f7733a2f7d0
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e0ff5103a60e'
down_revision = '7f7733a2f7d0'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    section_id = conn.execute(
        sa.text("SELECT id FROM nav_section WHERE name = 'Administration'")
    ).scalar_one_or_none()
    if section_id is None:
        return

    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM nav_item WHERE section_id = :sid AND page_slug = 'tenant_management'"
        ),
        {"sid": section_id},
    ).first()
    if exists:
        return

    max_seq = conn.execute(
        sa.text("SELECT COALESCE(MAX(sequence), 0) FROM nav_item WHERE section_id = :sid"),
        {"sid": section_id},
    ).scalar_one()

    conn.execute(
        sa.text(
            "INSERT INTO nav_item (section_id, page_slug, sequence, is_visible) "
            "VALUES (:sid, 'tenant_management', :seq, 1)"
        ),
        {"sid": section_id, "seq": max_seq + 1},
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM nav_item WHERE page_slug = 'tenant_management'"))
