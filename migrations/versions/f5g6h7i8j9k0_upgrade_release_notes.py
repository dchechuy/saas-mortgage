"""upgrade release_notes — add AI pipeline columns

Revision ID: f5g6h7i8j9k0
Revises: e4f5g6h7i8j9
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "f5g6h7i8j9k0"
down_revision = "e4f5g6h7i8j9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("release_note") as batch_op:
        # Make legacy fields nullable (they may be absent for AI-generated notes)
        batch_op.alter_column("title",            nullable=True,  existing_type=sa.String(255))
        batch_op.alter_column("summary_markdown", nullable=True,  existing_type=sa.Text)
        # New columns
        batch_op.add_column(sa.Column("codename",              sa.String(80),  nullable=True))
        batch_op.add_column(sa.Column("raw_summary",           sa.Text,        nullable=True))
        batch_op.add_column(sa.Column("content_html",          sa.Text,        nullable=True))
        batch_op.add_column(sa.Column("status",                sa.String(20),  nullable=False,
                                      server_default="published"))
        batch_op.add_column(sa.Column("published_at",          sa.DateTime,    nullable=True))
        batch_op.add_column(sa.Column("changelog_commit_hash", sa.String(40),  nullable=True))


def downgrade():
    with op.batch_alter_table("release_note") as batch_op:
        batch_op.drop_column("changelog_commit_hash")
        batch_op.drop_column("published_at")
        batch_op.drop_column("status")
        batch_op.drop_column("content_html")
        batch_op.drop_column("raw_summary")
        batch_op.drop_column("codename")
        batch_op.alter_column("summary_markdown", nullable=False, existing_type=sa.Text)
        batch_op.alter_column("title",            nullable=False, existing_type=sa.String(255))
