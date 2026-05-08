import os

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..access import permission_required
from ..activity_logger import log_activity
from ..extensions import db
from ..models import Role, User
from ..page_registry import PAGES

users_bp = Blueprint("users", __name__, url_prefix="/users")

ALLOWED_AVATAR_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _role_names() -> list[str]:
    return [role.name for role in Role.query.order_by(Role.name).all()]


@users_bp.route("/")
@login_required
@permission_required("users", "view")
def list_users():
    users = User.query.order_by(User.username).all()
    roles = Role.query.order_by(Role.is_system.desc(), Role.name).all()
    user_counts = {role.name: User.query.filter_by(role=role.name, is_active=True).count() for role in roles}
    return render_template(
        "users/list.html",
        users=users,
        roles=roles,
        user_counts=user_counts,
        pages=PAGES,
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "User Management", "url": None},
        ],
    )


@users_bp.route("/add", methods=["GET", "POST"])
@login_required
@permission_required("users", "edit")
def add_user():
    roles = _role_names()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "member")

        if not username or not email or not password:
            flash("Username, email, and password are required.", "error")
        elif role not in roles:
            flash("Invalid role selected.", "error")
        elif User.query.filter_by(username=username).first():
            flash(f"Username '{username}' is already taken.", "error")
        elif User.query.filter_by(email=email).first():
            flash(f"Email '{email}' is already registered.", "error")
        else:
            user = User(
                username=username,
                email=email,
                role=role,
                first_name=request.form.get("first_name", "").strip() or None,
                last_name=request.form.get("last_name", "").strip() or None,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            log_activity(current_user, "user.created", page="User Management")
            flash(f"User '{username}' created.", "success")
            return redirect(url_for("users.list_users"))

    return render_template("users/edit.html", user=None, roles=roles)


@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("users", "edit")
def edit_user(user_id):
    user = db.get_or_404(User, user_id)
    roles = _role_names()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "member")

        if not username or not email:
            flash("Username and email are required.", "error")
        elif role not in roles:
            flash("Invalid role selected.", "error")
        else:
            existing_user = User.query.filter_by(username=username).first()
            existing_email = User.query.filter_by(email=email).first()
            if existing_user and existing_user.id != user.id:
                flash(f"Username '{username}' is already taken.", "error")
            elif existing_email and existing_email.id != user.id:
                flash(f"Email '{email}' is already registered.", "error")
            else:
                user.username = username
                user.email = email
                user.role = role
                user.first_name = request.form.get("first_name", "").strip() or None
                user.last_name = request.form.get("last_name", "").strip() or None
                new_password = request.form.get("password", "")
                if new_password:
                    user.set_password(new_password)
                    user.must_change_password = False
                db.session.commit()
                log_activity(current_user, "user.updated", page="User Management")
                flash(f"User '{username}' updated.", "success")
                return redirect(url_for("users.list_users"))

    return render_template("users/edit.html", user=user, roles=roles)


@users_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 10:
            flash("New password must be at least 10 characters.", "error")
        elif new_password != confirm_password:
            flash("New password and confirmation do not match.", "error")
        else:
            current_user.set_password(new_password)
            current_user.must_change_password = False
            db.session.commit()
            log_activity(current_user, "user.password_changed", page="User Management")
            flash("Password updated.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("users/change_password.html")


@users_bp.route("/<int:user_id>/toggle", methods=["POST"])
@login_required
@permission_required("users", "edit")
def toggle_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        action = "user.activated" if user.is_active else "user.deactivated"
        log_activity(current_user, action, page="User Management")
        flash(f"User '{user.username}' {'activated' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("users.list_users"))


@users_bp.route("/me/upload-avatar", methods=["POST"])
@login_required
def upload_avatar_self():
    _save_avatar(current_user)
    return redirect(request.referrer or url_for("main.dashboard"))


def _save_avatar(user: User) -> None:
    file = request.files.get("avatar")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        flash("Allowed formats: JPG, PNG, GIF, WEBP.", "error")
        return

    avatar_dir = current_app.config["AVATAR_UPLOAD_FOLDER"]
    os.makedirs(avatar_dir, exist_ok=True)
    filename = f"user_{user.id}.{ext}"
    for old in os.listdir(avatar_dir):
        if old.startswith(f"user_{user.id}."):
            os.remove(os.path.join(avatar_dir, old))
    file.save(os.path.join(avatar_dir, filename))
    user.avatar = filename
    db.session.commit()
    flash("Avatar updated.", "success")


@users_bp.route("/<int:user_id>/upload-avatar", methods=["POST"])
@login_required
@permission_required("users", "edit")
def upload_avatar(user_id):
    if not current_user.is_admin():
        abort(403)
    user = db.get_or_404(User, user_id)
    _save_avatar(user)
    return redirect(url_for("users.edit_user", user_id=user_id))

