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


def get_user_scope(page_slug: str) -> str:
    """Return 'all' or 'own' for the current user on the given page.

    Admins always get 'all'. Non-authenticated users get 'own'.
    """
    if not current_user.is_authenticated:
        return "own"
    if current_user.is_admin():
        return "all"

    from .models import Permission, Role

    role = Role.query.filter_by(name=current_user.role).first()
    permission = (
        Permission.query.filter_by(role_id=role.id, page_slug=page_slug).first()
        if role else None
    )
    return permission.scope if permission else "own"


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


def feature_required(key: str):
    """Block a route when the effective (tenant-override-aware) feature flag
    is disabled — a hidden nav item alone is not an authorization boundary,
    so surfaces behind a flag need this at the route too."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            from .feature_flags import is_feature_enabled

            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if not is_feature_enabled(key):
                flash("This feature is not currently enabled.", "error")
                return redirect(url_for("main.dashboard"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def cofficiency_admin_required(view_func):
    """Only Cofficiency administrators may manage tenants.

    Deliberately not just `permission_required` — is_admin() bypasses normal
    page-slug permission checks, which would otherwise let an external
    tenant's own admin-role user manage other tenants. Tenant switching
    grants workspace selection, not elevated permissions, so this checks
    home-tenant identity directly rather than relying on role bypass alone.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        from .tenant_context import is_cofficiency_user

        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not (current_user.is_admin() and is_cofficiency_user(current_user)):
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for("main.dashboard"))
        return view_func(*args, **kwargs)

    return wrapped

