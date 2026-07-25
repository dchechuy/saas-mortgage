import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..access import cofficiency_admin_required
from ..activity_logger import log_activity
from ..extensions import db
from ..models import Tenant
from ..tenant_context import can_switch_tenants

tenants_bp = Blueprint("tenants", __name__, url_prefix="/tenants")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "tenant"


def _unique_slug(base_slug: str, exclude_id: int = None) -> str:
    slug = base_slug
    suffix = 2
    while True:
        query = Tenant.query.filter_by(slug=slug)
        if exclude_id:
            query = query.filter(Tenant.id != exclude_id)
        if not query.first():
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


def _name_taken(name: str, exclude_id: int = None) -> bool:
    query = Tenant.query.filter(db.func.lower(Tenant.name) == name.strip().lower())
    if exclude_id:
        query = query.filter(Tenant.id != exclude_id)
    return query.first() is not None


def _is_safe_redirect_target(target: str) -> bool:
    return bool(target) and target.startswith("/") and not target.startswith("//") and "://" not in target


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


@tenants_bp.route("/add", methods=["POST"])
@login_required
@cofficiency_admin_required
def add_tenant():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Tenant name is required.", "error")
        return redirect(url_for("tenants.list_tenants"))
    if _name_taken(name):
        flash(f"A tenant named '{name}' already exists.", "error")
        return redirect(url_for("tenants.list_tenants"))

    slug = _unique_slug(_slugify(name))
    tenant = Tenant(name=name, slug=slug, is_active=True, is_protected=False)
    db.session.add(tenant)
    db.session.commit()
    log_activity(current_user, "tenant.created", page="Tenant Management")
    flash(f"Tenant '{name}' created.", "success")
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

    tenant.name = name
    db.session.commit()
    log_activity(current_user, "tenant.updated", page="Tenant Management")
    flash(f"Tenant '{name}' saved.", "success")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/<int:tenant_id>/archive", methods=["POST"])
@login_required
@cofficiency_admin_required
def archive_tenant(tenant_id):
    tenant = db.get_or_404(Tenant, tenant_id)
    if tenant.is_protected:
        flash("The Cofficiency tenant cannot be archived.", "error")
    else:
        tenant.is_active = False
        db.session.commit()
        log_activity(current_user, "tenant.archived", page="Tenant Management")
        flash(f"Tenant '{tenant.name}' archived.", "success")
    return redirect(url_for("tenants.list_tenants"))


@tenants_bp.route("/<int:tenant_id>/reactivate", methods=["POST"])
@login_required
@cofficiency_admin_required
def reactivate_tenant(tenant_id):
    tenant = db.get_or_404(Tenant, tenant_id)
    tenant.is_active = True
    db.session.commit()
    log_activity(current_user, "tenant.reactivated", page="Tenant Management")
    flash(f"Tenant '{tenant.name}' reactivated.", "success")
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
