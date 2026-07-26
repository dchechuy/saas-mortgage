"""Central active-tenant resolution and switching authorization.

`User.tenant_id` (home tenant) is immutable and never resolved here — it's
just a column. This module resolves *active* tenant: the workspace a user is
currently operating in, which for Cofficiency users can differ from their
home tenant.

Routes and templates must go through here rather than inventing their own
tenant-selection logic, per the PRD's central-service requirement.
"""
from flask import g, has_app_context
from flask_login import current_user

from .extensions import db
from .models import Tenant

_COFFICIENCY_SLUG = "cofficiency"
_UNSET = object()


def get_cofficiency_tenant() -> Tenant:
    """Return the protected Cofficiency tenant. Assumes the Phase 1 migration has run."""
    if has_app_context():
        cached = getattr(g, "_cofficiency_tenant", None)
        if cached is not None:
            return cached
    tenant = Tenant.query.filter_by(slug=_COFFICIENCY_SLUG).one()
    if has_app_context():
        g._cofficiency_tenant = tenant
    return tenant


def is_cofficiency_user(user=None) -> bool:
    """True when `user`'s immutable home tenant is Cofficiency (i.e. an internal user).

    Defaults to the current logged-in user.
    """
    user = user if user is not None else current_user
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return user.tenant_id == get_cofficiency_tenant().id


def can_switch_tenants(user=None) -> bool:
    """Only Cofficiency (internal) users may switch their active tenant workspace."""
    return is_cofficiency_user(user)


def get_active_tenant(user=None):
    """Resolve the tenant workspace `user` (default: current_user) is operating in.

    - Unauthenticated -> None.
    - External user -> always their immutable home tenant.
    - Cofficiency user -> their remembered `last_active_tenant_id`, if it
      references a currently-active tenant; otherwise falls back to Cofficiency.

    The database-backed `last_active_tenant_id` is the source of truth — this
    never trusts a tenant id from the session or request directly.
    """
    explicit_user = user is not None
    resolved_user = user if explicit_user else current_user

    # Only cache the common "resolve for the requesting user" path — an
    # explicit-user call (e.g. background attribution for a different actor)
    # must not read or clobber that per-request cache.
    if not explicit_user and has_app_context():
        cached = getattr(g, "_active_tenant", _UNSET)
        if cached is not _UNSET:
            return cached

    tenant = _resolve_active_tenant(resolved_user)

    if not explicit_user and has_app_context():
        g._active_tenant = tenant
    return tenant


def _resolve_active_tenant(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    if not is_cofficiency_user(user):
        return user.tenant

    remembered_id = user.last_active_tenant_id
    if remembered_id:
        remembered = db.session.get(Tenant, remembered_id)
        if remembered and remembered.is_active:
            return remembered

    return get_cofficiency_tenant()


def get_active_tenant_id(user=None):
    """Convenience wrapper returning just the id (or None)."""
    tenant = get_active_tenant(user)
    return tenant.id if tenant else None


def require_tenant_record(record) -> None:
    """Abort with 404 unless `record.tenant_id` matches the active tenant.

    A 404 (rather than 403) avoids confirming a cross-tenant record's
    existence to a client that guessed or reused its URL.
    """
    from flask import abort

    active_id = get_active_tenant_id()
    if active_id is None or getattr(record, "tenant_id", None) != active_id:
        abort(404)


class MissingTenantExternalIdError(Exception):
    """Raised by require_active_tenant_external_id when there's no
    server-resolved active tenant, or it has no skunkBOX external_id yet.
    A future cross-system call (customer asset/quality management, Phase 6+)
    must treat this as a hard stop — never fall back to a locally-invented
    or browser-supplied tenant id (PRD Phase 5: "A missing UUID blocks the
    cross-system operation safely")."""


def get_active_tenant_external_id(user=None) -> str | None:
    """The active tenant's skunkBOX external_id, resolved entirely
    server-side via get_active_tenant() — never from a request header, form
    field, or query string. This is the only sanctioned source of tenant
    identity for a future skunkBOX customer-management API call; per-tenant
    Integration credentials remain defense in depth alongside it, not a
    replacement (see docs/ARCHITECTURE.md "skunkBOX interim boundary")."""
    tenant = get_active_tenant(user)
    return tenant.external_id if tenant else None


def require_active_tenant_external_id(user=None) -> str:
    """Same as get_active_tenant_external_id, but raises instead of
    returning None — for a call site where proceeding without one would be
    unsafe. Do not catch this broadly and substitute a fallback value."""
    external_id = get_active_tenant_external_id(user)
    if not external_id:
        raise MissingTenantExternalIdError(
            "No skunkBOX-synced active tenant is available for this request."
        )
    return external_id
