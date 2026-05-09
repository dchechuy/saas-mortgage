"""Seed default nav sections (runs once via migration, never at startup)

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-05-09

"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
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

    # Wipe whatever is there (handles leftover duplicates from race-condition bug)
    conn.execute(sa.text("DELETE FROM nav_item"))
    conn.execute(sa.text("DELETE FROM nav_section"))

    for name, short_name, seq, slugs in DEFAULT_SECTIONS:
        result = conn.execute(
            sa.text("INSERT INTO nav_section (name, short_name, sequence) VALUES (:n, :s, :q)"),
            {"n": name, "s": short_name, "q": seq},
        )
        section_id = result.lastrowid
        for i, slug in enumerate(slugs, start=1):
            conn.execute(
                sa.text("INSERT INTO nav_item (section_id, page_slug, sequence, is_visible) VALUES (:sid, :slug, :seq, 1)"),
                {"sid": section_id, "slug": slug, "seq": i},
            )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM nav_item"))
    conn.execute(sa.text("DELETE FROM nav_section"))
