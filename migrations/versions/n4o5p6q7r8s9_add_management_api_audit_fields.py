"""add management API audit fields

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa


revision = "n4o5p6q7r8s9"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("api_request_log") as batch_op:
        batch_op.add_column(sa.Column("operation", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("target_identifier", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("correlation_id", sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table("api_request_log") as batch_op:
        batch_op.drop_column("correlation_id")
        batch_op.drop_column("target_identifier")
        batch_op.drop_column("operation")
