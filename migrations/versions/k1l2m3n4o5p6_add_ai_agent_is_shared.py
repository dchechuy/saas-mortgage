"""add AiAgent.is_shared + uq_ai_agent_tenant_skunkbox_agent

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-07-26

Phase 6 of the Cross-System Tenant AI Assets initiative
(docs/prompts/Cross-System Tenant AI Assets - PRD.md).

`is_shared=True` marks a local `ai_agent` row as a system-managed mirror of
a Cofficiency Shared skunkBOX Agent, upserted by
app/services/agent_sync.py — as opposed to a tenant's own hand-configured
row. Existing rows are all hand-configured, so they default to False.

Also adds a uniqueness constraint on (tenant_id, skunkbox_agent_id):
without it, a customer admin could hand-create a local agent pointing at
the same skunkBOX Persona id that agent_sync.py later (or already) mirrors
as Shared, producing two local rows for one skunkBOX agent under the same
tenant — "ambiguous duplicate ownership" the Phase 6 prompt explicitly
calls out to avoid. A pre-existing real-world duplicate would abort this
migration rather than silently pick one; none exist in the current dev
database (verified: `SELECT tenant_id, skunkbox_agent_id, COUNT(*) FROM
ai_agent GROUP BY 1, 2 HAVING COUNT(*) > 1` returns zero rows).
"""
import sqlalchemy as sa
from alembic import op

revision = 'k1l2m3n4o5p6'
down_revision = 'j0k1l2m3n4o5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("ai_agent")]

    dupes = conn.execute(sa.text('''
        SELECT tenant_id, skunkbox_agent_id, COUNT(*) c
        FROM ai_agent GROUP BY tenant_id, skunkbox_agent_id HAVING c > 1
    ''')).fetchall()
    if dupes:
        raise RuntimeError(
            f"[ai_agent is_shared migration] {len(dupes)} (tenant_id, skunkbox_agent_id) pair(s) "
            f"already have more than one local row — cannot add the uniqueness constraint until "
            f"these are manually resolved: {[(d[0], d[1], d[2]) for d in dupes]}"
        )

    with op.batch_alter_table("ai_agent", schema=None) as batch_op:
        if "is_shared" not in existing_cols:
            batch_op.add_column(sa.Column("is_shared", sa.Boolean(), nullable=False,
                                          server_default=sa.false()))
        batch_op.create_unique_constraint(
            "uq_ai_agent_tenant_skunkbox_agent", ["tenant_id", "skunkbox_agent_id"]
        )


def downgrade():
    with op.batch_alter_table("ai_agent", schema=None) as batch_op:
        batch_op.drop_constraint("uq_ai_agent_tenant_skunkbox_agent", type_="unique")
        batch_op.drop_column("is_shared")
