"""add Tenant.external_id — skunkBOX authoritative tenant UUID mapping

Revision ID: j0k1l2m3n4o5
Revises: b76334d75376
Create Date: 2026-07-26

Phase 5 of the Cross-System Tenant AI Assets initiative
(docs/prompts/Cross-System Tenant AI Assets - PRD.md).

skunkBOX is now the authoritative tenant registry. This adds Cophy's
immutable, unique mapping to skunkBOX's `Tenant.public_id` UUID.

Cofficiency and AdvantageFirst are mapped to skunkBOX's known, already-seeded
UUIDs (copied from saas-platform's Phase 1 migration
`ta12345678nt_create_tenant_registry.py`) — these two tenants are seeded
identically in both systems, so their cross-system identity is a fixed,
reviewed constant, never generated here.

Any OTHER pre-existing local tenant (there are none in the real Cophy
database as of this migration — verified via `instance/app.db`, which has
exactly Cofficiency + AdvantageFirst) has no way to know its skunkBOX-side
UUID, since skunkBOX has no record of it. Production must not silently
invent one (PRD §5: "Never generate conflicting cross-system UUIDs
independently in production") — this migration raises rather than guessing,
unless TENANT_SYNC_ALLOW_AUTO_UUID=1 is explicitly set (a deliberate
dev/test-only escape hatch), in which case it assigns a fresh random UUID
and leaves `sync_status='error'` so the reconciliation UI flags it for
manual review against skunkBOX rather than silently trusting it.
"""
import os
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = 'j0k1l2m3n4o5'
down_revision = 'b76334d75376'
branch_labels = None
depends_on = None

# Copied from saas-platform/migrations/versions/ta12345678nt_create_tenant_registry.py —
# the authoritative skunkBOX values. Do not regenerate.
COFFICIENCY_UUID = '3f9d9a2e-2b7a-4a63-9d1a-8e4c9c9b7a10'
ADVANTAGEFIRST_UUID = '7c1e6b44-5a3f-4e9a-9b52-1e3a7f6d2c88'


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c["name"] for c in inspector.get_columns("tenant")]

    with op.batch_alter_table("tenant", schema=None) as batch_op:
        if "external_id" not in existing_cols:
            batch_op.add_column(sa.Column("external_id", sa.String(length=36), nullable=True))
        if "last_synced_at" not in existing_cols:
            batch_op.add_column(sa.Column("last_synced_at", sa.DateTime(), nullable=True))
        if "sync_status" not in existing_cols:
            batch_op.add_column(sa.Column("sync_status", sa.String(length=20), nullable=False,
                                          server_default='unsynced'))

    now = datetime.utcnow()
    for slug, known_uuid in (("cofficiency", COFFICIENCY_UUID), ("advantagefirst", ADVANTAGEFIRST_UUID)):
        row = conn.execute(sa.text("SELECT id FROM tenant WHERE slug = :slug"), {"slug": slug}).fetchone()
        if row:
            conn.execute(
                sa.text('''
                    UPDATE tenant SET external_id = :uuid, sync_status = 'synced', last_synced_at = :now
                    WHERE id = :id
                '''),
                {"uuid": known_uuid, "now": now, "id": row[0]},
            )

    unmapped = conn.execute(sa.text('''
        SELECT id, name, slug FROM tenant WHERE external_id IS NULL
    ''')).fetchall()
    if unmapped:
        if os.environ.get("TENANT_SYNC_ALLOW_AUTO_UUID") == "1":
            for tenant_id, name, slug in unmapped:
                conn.execute(
                    sa.text('''
                        UPDATE tenant SET external_id = :uuid, sync_status = 'error', last_synced_at = NULL
                        WHERE id = :id
                    '''),
                    {"uuid": str(uuid.uuid4()), "id": tenant_id},
                )
            print(f"[tenant external_id migration] TENANT_SYNC_ALLOW_AUTO_UUID=1: assigned placeholder "
                  f"UUIDs to {len(unmapped)} pre-existing tenant(s) not known to skunkBOX "
                  f"(sync_status=error, needs manual reconciliation): "
                  f"{[(t[0], t[2]) for t in unmapped]}")
        else:
            names = ", ".join(f"{name!r} (id={tid}, slug={slug!r})" for tid, name, slug in unmapped)
            raise RuntimeError(
                f"[tenant external_id migration] {len(unmapped)} tenant(s) exist locally with no known "
                f"skunkBOX UUID: {names}. These predate cross-system sync and skunkBOX has no record of "
                f"them — this migration will not invent a cross-system identity in production. Either "
                f"provision them in skunkBOX first and re-run with an updated mapping, or set "
                f"TENANT_SYNC_ALLOW_AUTO_UUID=1 for a disposable dev/test database only."
            )

    still_null = conn.execute(sa.text("SELECT COUNT(*) FROM tenant WHERE external_id IS NULL")).scalar()
    if still_null:
        raise RuntimeError(
            f"[tenant external_id migration] {still_null} tenant(s) still have no external_id — aborting."
        )

    with op.batch_alter_table("tenant", schema=None) as batch_op:
        batch_op.alter_column("external_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_unique_constraint("uq_tenant_external_id", ["external_id"])


def downgrade():
    with op.batch_alter_table("tenant", schema=None) as batch_op:
        batch_op.drop_constraint("uq_tenant_external_id", type_="unique")
        batch_op.alter_column("external_id", existing_type=sa.String(length=36), nullable=True)
        batch_op.drop_column("sync_status")
        batch_op.drop_column("last_synced_at")
        batch_op.drop_column("external_id")
