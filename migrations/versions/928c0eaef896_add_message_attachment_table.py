"""add message_attachment table

Revision ID: 928c0eaef896
Revises: 0c10cb9a0c0b
Create Date: 2026-05-09 11:45:16.276310

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '928c0eaef896'
down_revision = '0c10cb9a0c0b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'message_attachment',
        sa.Column('id',                     sa.Integer(),     nullable=False),
        sa.Column('message_id',             sa.Integer(),     nullable=False),
        sa.Column('skunkbox_attachment_id', sa.Integer(),     nullable=False),
        sa.Column('original_filename',      sa.String(255),   nullable=False),
        sa.Column('mime_type',              sa.String(100),   nullable=False),
        sa.Column('file_category',          sa.String(20),    nullable=False),
        sa.Column('file_size_bytes',        sa.Integer(),     nullable=True),
        sa.Column('created_at',             sa.DateTime(),    nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['agent_message.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('message_attachment')
