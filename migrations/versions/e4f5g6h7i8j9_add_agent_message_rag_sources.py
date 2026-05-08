"""add rag_sources to agent_message

Revision ID: e4f5g6h7i8j9
Revises: d3e4f5g6h7i8
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "e4f5g6h7i8j9"
down_revision = "d3e4f5g6h7i8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("agent_message") as batch_op:
        batch_op.add_column(sa.Column("rag_sources", sa.Text, nullable=True))


def downgrade():
    with op.batch_alter_table("agent_message") as batch_op:
        batch_op.drop_column("rag_sources")
