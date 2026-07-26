"""add experiment table (local UI-continuity mirror only)

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-07-26

Phase 7 of the Cross-System Tenant AI Assets initiative
(docs/prompts/Cross-System Tenant AI Assets - PRD.md).

skunkBOX's Phase 4 management API has no `GET /experiments` list endpoint
(confirmed against saas-platform/app/routes/api_v1_management.py — only
create/get/results exist), so Cophy has no way to show an experiment
history list without remembering the ids itself. This table stores only
enough to build that list and re-derive which skunkBOX ids to poll — no
status/progress/metrics/results columns, since those must stay live-fetched
per the PRD's "do not recreate ... evaluation state machines locally".
"""
import sqlalchemy as sa
from alembic import op

revision = 'l2m3n4o5p6q7'
down_revision = 'k1l2m3n4o5p6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'experiment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('skunkbox_experiment_id', sa.Integer(), nullable=False),
        sa.Column('skunkbox_component_id', sa.Integer(), nullable=False),
        sa.Column('skunkbox_component_version_id', sa.Integer(), nullable=False),
        sa.Column('skunkbox_dataset_id', sa.Integer(), nullable=False),
        sa.Column('skunkbox_dataset_version_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name='fk_experiment_tenant_id'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], name='fk_experiment_created_by_user_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'skunkbox_experiment_id', name='uq_experiment_tenant_skunkbox_experiment'),
    )
    with op.batch_alter_table('experiment', schema=None) as batch_op:
        batch_op.create_index('ix_experiment_tenant_id', ['tenant_id'])


def downgrade():
    with op.batch_alter_table('experiment', schema=None) as batch_op:
        batch_op.drop_index('ix_experiment_tenant_id')
    op.drop_table('experiment')
