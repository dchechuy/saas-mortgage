from flask import Blueprint, render_template, url_for
from flask_login import login_required

from ..access import permission_required
from ..models import Attribute, Integration, LlmModel, ReleaseNote, Role, User

main_bp = Blueprint("main", __name__)


@main_bp.route("/dashboard")
@login_required
@permission_required("dashboard", "view")
def dashboard():
    stats = {
        "users": User.query.count(),
        "roles": Role.query.count(),
        "models": LlmModel.query.count(),
        "integrations": Integration.query.count(),
        "attributes": Attribute.query.count(),
        "releases": ReleaseNote.query.count(),
    }
    recent_releases = ReleaseNote.query.order_by(ReleaseNote.created_at.desc()).limit(5).all()
    return render_template(
        "main/dashboard.html",
        stats=stats,
        recent_releases=recent_releases,
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "Dashboard", "url": None},
        ],
    )

