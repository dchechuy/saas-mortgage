"""seed AI Quality nav section (Components/Datasets/Experiments)

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-07-26

Phase 7 of the Cross-System Tenant AI Assets initiative
(docs/prompts/Cross-System Tenant AI Assets - PRD.md).

Insert-only, like e0ff5103a60e_add_tenant_management_nav_item.py — never
wipes existing NavSection/NavItem rows (a live Cofficiency admin may have
already reordered/hidden things via the Sections editor). Creates the
section only if it doesn't already exist, and each item only if missing.
"""
from alembic import op
import sqlalchemy as sa

revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None

_ITEMS = ["components", "datasets", "experiments"]


def upgrade():
    conn = op.get_bind()

    section_id = conn.execute(
        sa.text("SELECT id FROM nav_section WHERE name = 'AI Quality'")
    ).scalar_one_or_none()

    if section_id is None:
        max_seq = conn.execute(sa.text("SELECT COALESCE(MAX(sequence), 0) FROM nav_section")).scalar_one()
        result = conn.execute(
            sa.text("INSERT INTO nav_section (name, short_name, sequence) VALUES ('AI Quality', 'AI Q', :seq)"),
            {"seq": max_seq + 1},
        )
        section_id = result.lastrowid

    max_item_seq = conn.execute(
        sa.text("SELECT COALESCE(MAX(sequence), 0) FROM nav_item WHERE section_id = :sid"),
        {"sid": section_id},
    ).scalar_one()

    for i, slug in enumerate(_ITEMS, start=1):
        exists = conn.execute(
            sa.text("SELECT 1 FROM nav_item WHERE section_id = :sid AND page_slug = :slug"),
            {"sid": section_id, "slug": slug},
        ).first()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO nav_item (section_id, page_slug, sequence, is_visible) "
                "VALUES (:sid, :slug, :seq, 1)"
            ),
            {"sid": section_id, "slug": slug, "seq": max_item_seq + i},
        )


def downgrade():
    conn = op.get_bind()
    section_id = conn.execute(
        sa.text("SELECT id FROM nav_section WHERE name = 'AI Quality'")
    ).scalar_one_or_none()
    if section_id is None:
        return
    conn.execute(sa.text("DELETE FROM nav_item WHERE section_id = :sid AND page_slug IN "
                         "('components', 'datasets', 'experiments')"), {"sid": section_id})
    remaining = conn.execute(
        sa.text("SELECT COUNT(*) FROM nav_item WHERE section_id = :sid"), {"sid": section_id}
    ).scalar_one()
    if remaining == 0:
        conn.execute(sa.text("DELETE FROM nav_section WHERE id = :sid"), {"sid": section_id})
