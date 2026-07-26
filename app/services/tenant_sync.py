"""Local-mirror upsert logic for skunkBOX-authoritative tenant data — shared
by app/routes/tenants.py (single-tenant lifecycle actions) and
app/routes/tenant_reconciliation.py / the `sync-tenants` CLI command (bulk
reconciliation). Never deletes a local row, never touches `User.tenant_id`.
"""
from datetime import datetime

from ..extensions import db
from ..models import Tenant


class TenantSyncError(Exception):
    """Raised when a remote tenant payload can't be safely upserted locally
    — e.g. it would collide with an unrelated local tenant's name/slug. The
    caller must not guess a resolution; report and skip."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def upsert_tenant_from_remote(remote: dict) -> Tenant:
    """Create or update the local mirror row for one skunkBOX tenant payload
    (the dict shape returned by app.skunkbox_client). Does not commit —
    caller controls the transaction boundary so a route can roll back
    cleanly on a later failure without half-applying a sync.
    """
    external_id = remote["public_id"]
    name = remote["name"]
    slug = remote["slug"]

    tenant = Tenant.query.filter_by(external_id=external_id).first()

    # Detect drift: a DIFFERENT local tenant already owns this name/slug.
    # Never silently rename/reslug over it — report and let a human resolve.
    name_conflict = Tenant.query.filter(
        db.func.lower(Tenant.name) == name.strip().lower(),
        Tenant.external_id != external_id,
    ).first()
    if name_conflict:
        raise TenantSyncError(
            "duplicate_name",
            f"Cannot sync '{name}' ({external_id}): local tenant #{name_conflict.id} "
            f"already uses that name under a different external_id "
            f"({name_conflict.external_id or 'none'}).",
        )
    slug_conflict = Tenant.query.filter(
        Tenant.slug == slug, Tenant.external_id != external_id,
    ).first()
    if slug_conflict:
        raise TenantSyncError(
            "duplicate_slug",
            f"Cannot sync '{name}' ({external_id}): local tenant #{slug_conflict.id} "
            f"already uses slug '{slug}' under a different external_id "
            f"({slug_conflict.external_id or 'none'}).",
        )

    now = datetime.utcnow()
    if tenant:
        tenant.name = name
        tenant.slug = slug
        tenant.is_active = remote["is_active"]
        tenant.is_protected = remote["is_protected"]
        tenant.sync_status = "synced"
        tenant.last_synced_at = now
    else:
        tenant = Tenant(
            name=name, slug=slug, external_id=external_id,
            is_active=remote["is_active"], is_protected=remote["is_protected"],
            sync_status="synced", last_synced_at=now,
        )
        db.session.add(tenant)
    return tenant


def mark_sync_error(tenant: Tenant) -> None:
    """Flag a local tenant as needing attention without changing anything
    else about it — used when a local mutation succeeded in skunkBOX but the
    local upsert itself then failed, or when reconciliation hits a
    TenantSyncError for it."""
    tenant.sync_status = "error"


def run_reconciliation(logger=None) -> dict:
    """Full reconciliation: fetch every tenant skunkBOX knows about, upsert
    each into the local mirror, commit one at a time so one bad row (a
    duplicate/drift conflict) doesn't block the rest. Returns a summary dict
    (no secrets in it — safe to log/flash verbatim, PRD §5 "Log
    reconciliation results without secrets").

    Never deletes a local tenant that skunkBOX didn't return — a local
    tenant with no matching remote isn't evidence it was deleted upstream
    (skunkBOX doesn't hard-delete tenants either); it's flagged 'error' for
    a human to investigate, not removed.
    """
    from .. import skunkbox_client

    summary = {"created": 0, "updated": 0, "conflicts": [], "fetch_error": None}
    try:
        remote_page = skunkbox_client.list_tenants()
    except Exception as exc:
        summary["fetch_error"] = str(exc)
        if logger:
            logger.error("Tenant reconciliation: failed to fetch tenant list from skunkBOX: %s", exc)
        return summary

    remote_tenants = remote_page.get("tenants", [])
    seen_external_ids = set()
    for remote in remote_tenants:
        seen_external_ids.add(remote["public_id"])
        existing = Tenant.query.filter_by(external_id=remote["public_id"]).first()
        try:
            upsert_tenant_from_remote(remote)
            db.session.commit()
            if existing:
                summary["updated"] += 1
            else:
                summary["created"] += 1
        except TenantSyncError as exc:
            db.session.rollback()
            summary["conflicts"].append({"external_id": remote["public_id"], "name": remote["name"],
                                         "code": exc.code, "message": exc.message})
            if logger:
                logger.warning("Tenant reconciliation conflict: %s", exc.message)

    # Local tenants with an external_id skunkBOX didn't return this round —
    # flag, never delete/deactivate locally on our own authority. Skipped
    # entirely if skunkBOX returned zero tenants (almost certainly a
    # transient/misconfigured response, not evidence every tenant vanished).
    local_only = Tenant.query.filter(~Tenant.external_id.in_(seen_external_ids)).all() if remote_tenants else []
    for tenant in local_only:
        if tenant.sync_status != "error":
            mark_sync_error(tenant)
    if local_only:
        db.session.commit()
    summary["missing_from_skunkbox"] = [t.external_id for t in local_only]

    if logger:
        logger.info(
            "Tenant reconciliation: %d created, %d updated, %d conflict(s), %d missing-from-skunkBOX",
            summary["created"], summary["updated"], len(summary["conflicts"]),
            len(summary["missing_from_skunkbox"]),
        )
    return summary
