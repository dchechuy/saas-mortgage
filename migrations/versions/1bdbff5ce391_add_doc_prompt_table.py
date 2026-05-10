"""add doc_prompt table

Revision ID: 1bdbff5ce391
Revises: b543b16784f2
Create Date: 2026-05-10 13:12:10.660441

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1bdbff5ce391'
down_revision = 'b543b16784f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'doc_prompt',
        sa.Column('id',          sa.Integer(),      nullable=False),
        sa.Column('key',         sa.String(40),     nullable=False),
        sa.Column('label',       sa.String(120),    nullable=False),
        sa.Column('prompt_text', sa.Text(),         nullable=False),
        sa.Column('created_at',  sa.DateTime(),     nullable=False),
        sa.Column('updated_at',  sa.DateTime(),     nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )


def downgrade():
    op.drop_table('doc_prompt')
