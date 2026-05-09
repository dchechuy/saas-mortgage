"""Wipe duplicate nav data, seed defaults, add unique constraints

Revision ID: i9j0k1l2m3n4
Revises: g7h8i9j0k1l2
Create Date: 2026-05-09

"""
from alembic import op
import sqlalchemy as sa

revision = 'i9j0k1l2m3n4'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None

DEFAULT_SECTIONS = [
    ("AI Agents",      "AI",    1, ["conversations", "learning_center"]),
    ("Administration", "Admin", 2, ["user_management", "system_config", "reporting"]),
    ("Documentation",  "Docs",  3, ["user_guides", "system_overview"]),
]


def upgrade():
    conn = op.get_bind()

    # 1. Wipe everything — removes all duplicates in one shot
    conn.execute(sa.text("DELETE FROM nav_item"))
    conn.execute(sa.text("DELETE FROM nav_section"))

    # 2. Re-insert clean defaults
    for name, short_name, seq, slugs in DEFAULT_SECTIONS:
        result = conn.execute(
            sa.text("INSERT INTO nav_section (name, short_name, sequence) VALUES (:n, :s, :q)"),
            {"n": name, "s": short_name, "q": seq},
        )
        section_id = result.lastrowid
        for i, slug in enumerate(slugs, start=1):
            conn.execute(
                sa.text("INSERT INTO nav_item (section_id, page_slug, sequence, is_visible) "
                        "VALUES (:sid, :slug, :seq, 1)"),
                {"sid": section_id, "slug": slug, "seq": i},
            )

    # 3. Add unique constraint on nav_item(section_id, page_slug) — batch mode for SQLite
    with op.batch_alter_table('nav_item') as batch_op:
        batch_op.create_unique_constraint('uq_nav_item_section_slug', ['section_id', 'page_slug'])


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM nav_item"))
    conn.execute(sa.text("DELETE FROM nav_section"))
    with op.batch_alter_table('nav_item') as batch_op:
        batch_op.drop_constraint('uq_nav_item_section_slug', type_='unique')
