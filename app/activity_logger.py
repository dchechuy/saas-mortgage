"""Lightweight helper for writing UserActivityLog rows.

Usage:
    from .activity_logger import log_activity
    log_activity(user=current_user, action="user.login", page="System")

The `page` parameter is a human-readable label shown in Reporting.
Keep action strings in the format  "resource.verb"  (e.g. "user.login").
"""
from flask import request as _flask_request


def reraise_if_testing() -> None:
    """Call from an `except Exception:` block that would otherwise swallow a
    logging failure. Re-raises the currently-handled exception when running
    under tests, so a schema/programming bug in a log-writing path fails
    loudly instead of silently vanishing as "no log row was written". In
    production this is a no-op — logging failures must never break the
    real request."""
    try:
        from flask import current_app
        if current_app and current_app.testing:
            raise
    except RuntimeError:
        pass  # no app context to check — nothing more we can do


# Map action strings to a display label for the Reporting UI
ACTION_LABELS: dict[str, str] = {
    # Auth
    "user.login":              "Logged In",
    "user.logout":             "Logged Out",
    # User management
    "user.created":            "Created User",
    "user.updated":            "Updated User",
    "user.deleted":            "Deleted User",
    "user.activated":          "Activated User",
    "user.deactivated":        "Deactivated User",
    "user.password_changed":   "Changed Password",
    # Conversations
    "conversation.started":    "Started Conversation",
    "conversation.archived":   "Archived Conversation",
    # AI Agents config
    "agent.created":           "Added AI Agent",
    "agent.updated":           "Updated AI Agent",
    "agent.activated":         "Activated AI Agent",
    "agent.deactivated":       "Deactivated AI Agent",
    # LLM Models config
    "llm.created":             "Added LLM Model",
    "llm.updated":             "Updated LLM Model",
    "llm.activated":           "Activated LLM Model",
    "llm.deactivated":         "Deactivated LLM Model",
    # Integrations config
    "integration.created":     "Added Integration",
    "integration.updated":     "Updated Integration",
    # Attributes config
    "attribute.saved":         "Updated Attributes",
    # Feature flags
    "flag.toggled":            "Toggled Feature Flag",
    "flag.reset":              "Reset Feature Flag to Default",
    # Release notes
    "release_notes.generated": "Generated Release Notes",
    # Tenants
    "tenant.created":          "Created Tenant",
    "tenant.updated":          "Updated Tenant",
    "tenant.archived":         "Archived Tenant",
    "tenant.reactivated":      "Reactivated Tenant",
    "tenant.switched":         "Switched Tenant",
}


def log_activity(user, action: str, page: str | None = None, tenant_id: int | None = None) -> None:
    """Append one UserActivityLog row. Safe to call inside a request context.

    Args:
        user:      A User model instance (or None for anonymous).
        action:    Dot-namespaced action string, e.g. "user.login".
        page:      Optional human-readable page / section name.
        tenant_id: Explicit tenant to attribute the event to (e.g. the
                   destination tenant of a switch). Defaults to `user`'s
                   currently resolved active tenant — the actor's active
                   workspace at the time of the action, not their home
                   tenant. A Cofficiency user working in another tenant
                   produces activity for that tenant, not for Cofficiency.
    """
    try:
        from .extensions import db
        from .models import UserActivityLog
        from .tenant_context import get_active_tenant_id

        resolved_tenant_id = tenant_id if tenant_id is not None else get_active_tenant_id(user)
        if resolved_tenant_id is None:
            # No auditable tenant context (e.g. anonymous/failed-auth action) — nothing to log.
            return

        ip = None
        try:
            ip = _flask_request.remote_addr
        except RuntimeError:
            pass  # outside request context

        log = UserActivityLog(
            tenant_id=resolved_tenant_id,
            user_id=user.id if user else None,
            action=action,
            page=page,
            ip_address=ip,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        # Never let logging failures crash the main request
        reraise_if_testing()
