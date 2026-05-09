from flask import Blueprint, flash, redirect, request, url_for
from flask_login import current_user, login_required

from ..access import permission_required
from ..extensions import db
from ..models import Permission, Role, User
from ..page_registry import ACCESS_LEVELS, PAGES

permissions_bp = Blueprint("permissions", __name__, url_prefix="/permissions")


@permissions_bp.route("/add", methods=["POST"])
@login_required
@permission_required("permissions", "edit")
def add_role():
    name = request.form.get("name", "").strip().lower()
    if not name:
        flash("Role name is required.", "error")
    elif Role.query.filter_by(name=name).first():
        flash(f"Role '{name}' already exists.", "error")
    else:
        role = Role(name=name, is_system=False)
        db.session.add(role)
        db.session.flush()
        for page in PAGES:
            db.session.add(Permission(role_id=role.id, page_slug=page["slug"], access_level="no_access"))
        db.session.commit()
        flash(f"Role '{name}' created.", "success")
    return redirect(url_for("users.list_users") + "#permissions")


@permissions_bp.route("/<int:role_id>/save", methods=["POST"])
@login_required
@permission_required("permissions", "edit")
def save_role(role_id):
    role = db.get_or_404(Role, role_id)
    if role.is_protected:
        flash("System roles cannot be modified.", "error")
        return redirect(url_for("users.list_users") + "#permissions")

    old_name = role.name
    new_name = request.form.get("name", "").strip().lower()
    if not new_name:
        flash("Role name is required.", "error")
        return redirect(url_for("users.list_users") + "#permissions")

    duplicate = Role.query.filter_by(name=new_name).first()
    if duplicate and duplicate.id != role.id:
        flash(f"Role '{new_name}' already exists.", "error")
        return redirect(url_for("users.list_users") + "#permissions")

    role.name = new_name
    if old_name != new_name:
        User.query.filter_by(role=old_name).update({"role": new_name})

    for page in PAGES:
        level = request.form.get(f"perm_{page['slug']}", "no_access")
        if level not in ACCESS_LEVELS:
            level = "no_access"
        permission = Permission.query.filter_by(role_id=role.id, page_slug=page["slug"]).first()
        if permission:
            permission.access_level = level
        else:
            db.session.add(Permission(role_id=role.id, page_slug=page["slug"], access_level=level))

    db.session.commit()
    flash(f"Role '{new_name}' saved.", "success")
    return redirect(url_for("users.list_users") + "#permissions")


@permissions_bp.route("/<int:role_id>/delete", methods=["POST"])
@login_required
@permission_required("permissions", "edit")
def delete_role(role_id):
    if not current_user.is_admin():
        return redirect(url_for("agents.list_conversations"))

    role = db.get_or_404(Role, role_id)
    if role.is_protected:
        flash("System roles cannot be deleted.", "error")
    elif User.query.filter_by(role=role.name).count() > 0:
        flash("Reassign users before deleting this role.", "error")
    else:
        db.session.delete(role)
        db.session.commit()
        flash(f"Role '{role.name}' deleted.", "success")
    return redirect(url_for("users.list_users") + "#permissions")
