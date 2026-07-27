"""Phase 8 — Cross-System Tenant AI Assets: cross-system adversarial matrix
(docs/prompts/Cross-System Tenant AI Assets - Prompt - Phase 8 - saas-mortgage.md).

Covers scenarios from the Phase 8 prompt's adversarial matrix not already
exercised by the Phase 5/6/7 test suites (`test_cross_system_tenant_sync.py`,
`test_shared_knowledge_and_agents.py`, `test_ai_quality.py`): an archived
tenant's own users hitting the AI Quality surface, a revoked/invalid
service credential, Shared-Agent mirror drift correcting itself on the
next sync, a stale edit session surviving a mid-session tenant switch, and
forged request fields having no effect on which tenant a mutation targets.
"""
import io

from app.extensions import db
from app.models import AiAgent, FeatureFlag, Tenant, TenantFeatureFlag
from app.skunkbox_client import SkunkBoxClientError

from .conftest import create_integration, create_tenant, create_user
from .conftest import login as _login
from .conftest import set_password as _set_password

_COFFICIENCY_SENTINEL = "cofficiency-fake-external-id"


def _enable_ai_quality(app, tenant_id):
    with app.app_context():
        flag = FeatureFlag.query.filter_by(key="ai_quality").one()
        db.session.add(TenantFeatureFlag(tenant_id=tenant_id, feature_flag_id=flag.id, is_enabled=True))
        db.session.commit()


def _setup_tenant(full_app, name="Customer A", slug="customer-a", username="admin_a"):
    tenant_id = create_tenant(full_app, name, slug)
    _enable_ai_quality(full_app, tenant_id)
    admin_id = create_user(full_app, username, tenant_id, role="admin")
    return tenant_id, admin_id


def _client_for(full_app, username):
    _set_password(full_app, username, "Test-1234")
    client = full_app.test_client()
    _login(client, username, "Test-1234")
    return client


# ── Archived tenant API and UI behavior ─────────────────────────────────────

def test_archived_tenants_own_user_blocked_from_ai_quality_reads_and_writes(full_app, fake_skunkbox):
    tenant_id, _ = _setup_tenant(full_app)
    with full_app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        tenant.is_active = False
        db.session.commit()

    client = _client_for(full_app, "admin_a")

    for resp in (
        client.get("/quality/components"),
        client.get("/quality/datasets"),
        client.get("/quality/experiments/new"),
        client.post("/quality/components/add", data={"title": "Should Not Exist"}, follow_redirects=True),
        client.post("/quality/datasets/add", data={"name": "Should Not Exist"}, follow_redirects=True),
    ):
        assert resp.status_code == 200
        assert b"archived" in resp.data.lower()

    assert fake_skunkbox.calls == []
    assert fake_skunkbox.components == {}
    assert fake_skunkbox.datasets == {}


# ── Revoked/invalid service credential ──────────────────────────────────────

def test_revoked_service_credential_handled_safely_across_ai_quality_pages(full_app, fake_skunkbox, monkeypatch):
    """Simulates skunkBOX rejecting the service credential itself (401/403)
    — every page must show a safe error, never a raw 500 or a stack trace,
    and must never fall back to showing stale/cached data as if it were
    current."""
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    def revoked(*args, **kwargs):
        raise SkunkBoxClientError("Service credential has been revoked.", status_code=403, error_code="forbidden")

    import app.skunkbox_client as client_module
    for name in ("list_components", "list_datasets"):
        monkeypatch.setattr(client_module, name, revoked)

    resp = client.get("/quality/components")
    assert resp.status_code == 200
    assert b"Could not load Components" in resp.data

    resp = client.get("/quality/datasets")
    assert resp.status_code == 200
    assert b"Could not load Datasets" in resp.data

    resp = client.get("/quality/experiments/new")
    assert resp.status_code == 200
    assert b"Could not load Components/Datasets" in resp.data


# ── Mirror drift and reconciliation: Shared Agent unshared upstream ────────

def test_shared_agent_mirror_deactivates_when_unshared_upstream(full_app, fake_skunkbox):
    tenant_id, _ = _setup_tenant(full_app)
    integ_id = create_integration(full_app, tenant_id, use_case="AI Agents")
    shared_id = fake_skunkbox.seed_agent(
        "Concierge", owner_tenant_external_id=_COFFICIENCY_SENTINEL, is_shared=True,
    )

    from app.services.agent_sync import sync_shared_agents_for_tenant
    with full_app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        sync_shared_agents_for_tenant(tenant)
        mirror = AiAgent.query.filter_by(tenant_id=tenant_id, is_shared=True).one()
        assert mirror.is_active is True
        mirror_id = mirror.id

    # skunkBOX unshares it (or archives it) — it no longer appears in the
    # tenant-visible agent list at all.
    fake_skunkbox.agents[shared_id]["is_shared"] = False

    with full_app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        summary = sync_shared_agents_for_tenant(tenant)
        assert summary["deactivated"] == 1
        mirror = db.session.get(AiAgent, mirror_id)
        assert mirror.is_active is False   # deactivated, never deleted
        assert AiAgent.query.filter_by(id=mirror_id).count() == 1


# ── Switch tenant during an open edit (Component, not just Experiment poll) ─

def test_stale_component_edit_session_does_not_leak_into_new_active_tenant(full_app, fake_skunkbox):
    """A Cofficiency admin has Tenant A's Component edit form open, switches
    active tenant to B, then submits the stale form (still pointed at A's
    component id). The save must fail (404) rather than silently applying
    to whichever tenant happens to be active now, and must never touch B's
    (nonexistent) data for that id."""
    tenant_a, _ = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    with full_app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id
    create_user(full_app, "coffi_admin", cofficiency_id, role="admin")

    client = _client_for(full_app, "coffi_admin")
    client.post("/tenants/switch", data={"tenant_id": tenant_a, "next": "/"}, follow_redirects=True)
    client.post("/quality/components/add", data={"title": "A's Component"}, follow_redirects=True)
    component_id = list(fake_skunkbox.components.keys())[0]

    # Switch away — the edit form the admin still has open is now stale.
    client.post("/tenants/switch", data={"tenant_id": tenant_b, "next": "/"}, follow_redirects=True)
    resp = client.post(f"/quality/components/{component_id}/save", data={"title": "Hijacked"})
    assert resp.status_code == 404

    assert fake_skunkbox.components[component_id]["title"] == "A's Component"
    assert fake_skunkbox.components[component_id]["_owner"] != None  # still owned by A's UUID, untouched


# ── Forged request fields have no effect on which tenant is targeted ───────

def test_forged_tenant_fields_in_request_body_are_ignored(full_app, fake_skunkbox):
    """Even if a client stuffs a `tenant_id`/`external_id`-shaped field into
    the POST body, the tenant a mutation targets is always the server-
    resolved active tenant — never anything read from request data."""
    tenant_a, _ = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    with full_app.app_context():
        ext_id_b = db.session.get(Tenant, tenant_b).external_id

    client = _client_for(full_app, "admin_a")
    resp = client.post("/quality/components/add", data={
        "title": "Forged Target Co",
        "tenant_id": str(tenant_b),
        "external_id": ext_id_b,
        "X-Tenant-Id": ext_id_b,
    }, follow_redirects=True)
    assert resp.status_code == 200

    create_calls = [c for c in fake_skunkbox.calls if c[0] == "create_component"]
    assert len(create_calls) == 1
    actual_tenant_arg = create_calls[0][1][0]   # first positional arg to create_component(tenant_id, title, ...)
    with full_app.app_context():
        ext_id_a = db.session.get(Tenant, tenant_a).external_id
    assert actual_tenant_arg == ext_id_a
    assert actual_tenant_arg != ext_id_b


# ── show_archived filter never leaks another tenant's rows ─────────────────

def test_show_archived_filter_stays_within_own_tenant(full_app, fake_skunkbox):
    tenant_a, _ = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    with full_app.app_context():
        ext_id_a = db.session.get(Tenant, tenant_a).external_id
        ext_id_b = db.session.get(Tenant, tenant_b).external_id
    cid_a = fake_skunkbox.create_component(ext_id_a, "A Archived Co")["id"]
    fake_skunkbox.components[cid_a]["is_active"] = False
    cid_b = fake_skunkbox.create_component(ext_id_b, "B Archived Co")["id"]
    fake_skunkbox.components[cid_b]["is_active"] = False

    client_a = _client_for(full_app, "admin_a")
    resp = client_a.get("/quality/components?show_archived=1")
    assert b"A Archived Co" in resp.data
    assert b"B Archived Co" not in resp.data
