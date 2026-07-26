import uuid

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .. import skunkbox_client
from ..access import cofficiency_admin_required
from ..activity_logger import log_activity
from ..extensions import db
from ..models import Tenant
from ..services.tenant_sync import TenantSyncError, upsert_tenant_from_remote
from ..skunkbox_client import SkunkBoxClientError
from ..tenant_context import can_switch_tenants

tenants_bp = Blueprint("tenants", __name__, url_prefix="/tenants")


def _name_taken(name: str, exclude_id: int = None) -> bool:
    query = Tenant.query.filter(db.func.lower(Tenant.name) == name.strip().lower())
    if exclude_id:
        query = query.filter(Tenant.id != exclude_id)
    return query.first() is not None


def _is_safe_redirect_target(target: str) -> bool:
    return bool(target) and target.startswith("/") and not target.startswith("//") and "://" not in target


def _apply_remote_and_commit(remote: dict, success_message: str, activity_action: str):
    """Shared tail of every lifecycle route below: upsert the local mirror
    from skunkBOX's authoritative response and commit. skunkBOX has already
    accepted the mutation by the time this runs — a failure here is a
    *local mirror* failure, not an authoritative one, so it's reported as
    recoverable (fix via reconciliation) rather than treated as if the
    whole operation failed."""
    try:
        tenant = upsert_tenant_from_remote(remote)
        db.session.commit()
    except TenantSyncError as exc:
        db.session.rollback()
        flash(
            f"skunkBOX accepted this change, but the local mirror could not be updated "
            f"({exc.message}). Run tenant reconciliation to resolve this.", "error",
        )
        return None
    except Exception:
        db.session.rollback()
        flash(
            "skunkBOX accepted this change, but saving it locally failed unexpectedly. "
            "Run tenant reconciliation to resolve this.", "error",
        )
        return None

    log_activity(current_user, activity_action, page="Tenant Management")
    flash(success_message, "success")
    return tenant


@tenants_bp.route("/")
@login_required
@cofficiency_admin_required
def list_tenants():
    tenants = Tenant.query.order_by(Tenant.is_active.desc(), Tenant.name).all()
    return render_template(
        "tenants/list.html",
        tenants=tenants,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Tenant Management", "url": None},
        ],
    )


@tenants_bp.route("/sync", methods=["POST"])
@login_required
@cofficiency_admin_required
def sync_tenants():
    """Manual reconciliation trigger — same logic as the `sync-tenants` CLI
    command (app/cli.py), for a Cofficiency admin who doesn't want to wait
    for the scheduled run."""
    from ..services.tenant_sync import run_reconciliation

    summary = run_reconciliation()
    if summary["fetch_error"]:
        flash(f"Could not reach skunkBOX to sync tenants: {summary['fetch_error']}", "error")
    else:
        parts = [f"{summary['created']} created", f"{summary['updated']} updated"]
        if summary["conflicts"]:
            parts.append(f"{len(summary['conflicts'])} conflict(s) need review")
        if summary["missing_from_skunkbox"]:
            parts.append(f"{len(summary['missing_from_skunkbox'])} local tenant(s) not returned by skunkBOX")
        flash("Tenant sync complete: " + ", ".join(parts) + ".",
             "warning" if (summary["conflicts"] or summary["missing_from_skunkbox"]) else "success")
        log_activity(current_user, "tenant.synced", page="Tenant Management")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/add", methods=["POST"])
@login_required
@cofficiency_admin_required
def add_tenant():
    """Create is authoritative-first: skunkBOX accepts (or rejects) the new
    tenant before any local row exists at all — there is no local-only
    creation path (PRD Phase 5: "Do not permit a local-only lifecycle
    mutation")."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Tenant name is required.", "error")
        return redirect(url_for("tenants.list_tenants"))
    if _name_taken(name):
        flash(f"A tenant named '{name}' already exists.", "error")
        return redirect(url_for("tenants.list_tenants"))

    idempotency_key = str(uuid.uuid4())
    try:
        remote = skunkbox_client.create_tenant(name, idempotency_key=idempotency_key)
    except SkunkBoxClientError as exc:
        flash(f"Could not create tenant in skunkBOX: {exc}", "error")
        return redirect(url_for("tenants.list_tenants"))

    _apply_remote_and_commit(remote, f"Tenant '{name}' created.", "tenant.created")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/<int:tenant_id>/edit", methods=["POST"])
@login_required
@cofficiency_admin_required
def edit_tenant(tenant_id):
    tenant = db.get_or_404(Tenant, tenant_id)
    if tenant.is_protected:
        flash("The Cofficiency tenant cannot be renamed.", "error")
        return redirect(url_for("tenants.list_tenants"))

    name = request.form.get("name", "").strip()
    if not name:
        flash("Tenant name is required.", "error")
        return redirect(url_for("tenants.list_tenants"))
    if _name_taken(name, exclude_id=tenant.id):
        flash(f"A tenant named '{name}' already exists.", "error")
        return redirect(url_for("tenants.list_tenants"))

    try:
        remote = skunkbox_client.update_tenant(tenant.external_id, name)
    except SkunkBoxClientError as exc:
        flash(f"Could not update tenant in skunkBOX: {exc}", "error")
        return redirect(url_for("tenants.list_tenants"))

    _apply_remote_and_commit(remote, f"Tenant '{name}' saved.", "tenant.updated")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/<int:tenant_id>/archive", methods=["POST"])
@login_required
@cofficiency_admin_required
def archive_tenant(tenant_id):
    tenant = db.get_or_404(Tenant, tenant_id)
    if tenant.is_protected:
        flash("The Cofficiency tenant cannot be archived.", "error")
        return redirect(url_for("tenants.list_tenants"))

    try:
        remote = skunkbox_client.archive_tenant(tenant.external_id)
    except SkunkBoxClientError as exc:
        flash(f"Could not archive tenant in skunkBOX: {exc}", "error")
        return redirect(url_for("tenants.list_tenants"))

    _apply_remote_and_commit(remote, f"Tenant '{tenant.name}' archived.", "tenant.archived")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/<int:tenant_id>/reactivate", methods=["POST"])
@login_required
@cofficiency_admin_required
def reactivate_tenant(tenant_id):
    tenant = db.get_or_404(Tenant, tenant_id)

    try:
        remote = skunkbox_client.reactivate_tenant(tenant.external_id)
    except SkunkBoxClientError as exc:
        flash(f"Could not reactivate tenant in skunkBOX: {exc}", "error")
        return redirect(url_for("tenants.list_tenants"))

    _apply_remote_and_commit(remote, f"Tenant '{tenant.name}' reactivated.", "tenant.reactivated")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/switch", methods=["POST"])
@login_required
def switch_tenant():
    if not can_switch_tenants(current_user):
        flash("You do not have permission to switch tenants.", "error")
        return redirect(url_for("main.dashboard"))

    target_id = request.form.get("tenant_id", type=int)
    target = Tenant.query.filter_by(id=target_id, is_active=True).first() if target_id else None

    next_url = request.form.get("next", "")
    safe_next = next_url if _is_safe_redirect_target(next_url) else url_for("main.dashboard")

    if not target:
        flash("Select a valid, active tenant to switch to.", "error")
        return redirect(safe_next)

    current_user.last_active_tenant_id = target.id
    db.session.commit()
    log_activity(current_user, "tenant.switched", page="System", tenant_id=target.id)
    flash(f"Switched to {target.name}.", "success")
    return redirect(safe_next)
