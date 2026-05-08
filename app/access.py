from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

from .page_registry import ACCESS_LEVELS


def user_has_access(page_slug: str, min_level: str = "view") -> bool:
    """Check whether the current user has at least `min_level` access to `page_slug`.

    Usable in route logic as well as the inject_permissions context processor.
    Admin role always returns True.
    """
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin():
        return True

    from .models import Permission, Role

    role = Role.query.filter_by(name=current_user.role).first()
    permission = (
        Permission.query.filter_by(role_id=role.id, page_slug=page_slug).first()
        if role else None
    )
    level = permission.access_level if permission else "no_access"
    return ACCESS_LEVELS.index(level) >= ACCESS_LEVELS.index(min_level)


def permission_required(page_slug: str, min_level: str = "view"):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not user_has_access(page_slug, min_level):
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for("main.dashboard"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator

