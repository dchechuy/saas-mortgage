from flask import Blueprint, render_template, url_for
from flask_login import login_required

from ..access import permission_required
from ..models import Attribute, Integration, LlmModel, ReleaseNote, Role, User
from ..tenant_context import get_active_tenant_id

main_bp = Blueprint("main", __name__)


@main_bp.route("/dashboard")
@login_required
@permission_required("dashboard", "view")
def dashboard():
    active_tenant_id = get_active_tenant_id()
    stats = {
        "users": User.query.filter_by(tenant_id=active_tenant_id).count(),
        "roles": Role.query.count(),  # global template count, not tenant-owned
        "models": LlmModel.query.filter_by(tenant_id=active_tenant_id).count(),
        "integrations": Integration.query.filter_by(tenant_id=active_tenant_id).count(),
        "attributes": Attribute.query.filter_by(tenant_id=active_tenant_id).count(),
        "releases": ReleaseNote.query.count(),  # global, shared across tenants
    }
    recent_releases = ReleaseNote.query.order_by(ReleaseNote.created_at.desc()).limit(5).all()
    return render_template(
        "main/dashboard.html",
        stats=stats,
        recent_releases=recent_releases,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Dashboard", "url": None},
        ],
    )

