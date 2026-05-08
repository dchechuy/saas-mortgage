"""add use_case to integration

Revision ID: c2d3e4f5g6h7
Revises: b1c2d3e4f5g6
Create Date: 2026-05-07

"""
from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5g6h7"
down_revision = "b1c2d3e4f5g6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("integration") as batch_op:
        batch_op.add_column(
            sa.Column("use_case", sa.String(40), nullable=False, server_default="AI Agents")
        )


def downgrade():
    with op.batch_alter_table("integration") as batch_op:
        batch_op.drop_column("use_case")
