from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..activity_logger import log_activity
from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    return redirect(url_for("agents.list_conversations"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("agents.list_conversations"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "error")
        elif not user.is_active:
            flash("Your account is inactive.", "error")
        else:
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            log_activity(user=user, action="user.login", page="System")
            if user.must_change_password:
                flash("Please change the default password before continuing.", "warning")
                return redirect(url_for("users.change_password"))
            return redirect(url_for("agents.list_conversations"))

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
