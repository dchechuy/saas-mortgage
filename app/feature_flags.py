"""Effective feature-flag resolution: global catalogue + per-tenant overrides.

`FeatureFlag` is the global catalogue and default state. `TenantFeatureFlag`
holds active-tenant overrides. This is the one place that resolves
*effective* state — routes/templates/nav must go through here rather than
reading `FeatureFlag.is_enabled` directly for anything tenant-facing.
"""
from .models import FeatureFlag, TenantFeatureFlag
from .tenant_context import get_active_tenant_id


def effective_feature_flags(tenant=None) -> dict:
    """Return {key: bool} for every known flag, with the active tenant's
    override applied where one exists. Unknown/missing tenant falls back to
    the global default for every flag."""
    tenant_id = tenant.id if tenant is not None else get_active_tenant_id()

    flags = {f.key: f.is_enabled for f in FeatureFlag.query.all()}
    if tenant_id is None:
        return flags

    overrides = (
        FeatureFlag.query
        .with_entities(FeatureFlag.key, TenantFeatureFlag.is_enabled)
        .join(TenantFeatureFlag, TenantFeatureFlag.feature_flag_id == FeatureFlag.id)
        .filter(TenantFeatureFlag.tenant_id == tenant_id)
        .all()
    )
    for key, is_enabled in overrides:
        flags[key] = is_enabled
    return flags


def is_feature_enabled(key: str, tenant=None) -> bool:
    """True unless a flag row explicitly disables it — matches the existing
    fail-open convention (see app/__init__.py's inject_feature_flags), so a
    pending migration or unseeded flag never hides UI/routes by accident."""
    return effective_feature_flags(tenant).get(key, True)
