"""fix: ensure permission.scope column exists

Pre-existing bug discovered while testing Phase 2 from a fresh install:
migration 11b469c6d972 is titled "add scope to permission" but its actual
body only drops nav_item/nav_section unique constraints — it never adds the
column, even though app/models.py has required Permission.scope since before
that migration. Real deployed databases already have the column (added
out-of-band, not through any migration in this repo), so this is guarded to
be a no-op wherever it's already present.

Revision ID: b76334d75376
Revises: e0ff5103a60e
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b76334d75376'
down_revision = 'e0ff5103a60e'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"] for c in inspector.get_columns("permission")}
    if "scope" not in cols:
        with op.batch_alter_table("permission") as batch_op:
            batch_op.add_column(
                sa.Column("scope", sa.String(length=10), nullable=False, server_default="own")
            )


def downgrade():
    # Intentionally a no-op. Removing the column here could break installs
    # that already had it before this fix existed (added out-of-band).
    pass
