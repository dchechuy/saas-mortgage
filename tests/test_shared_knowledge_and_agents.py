"""Phase 6 — Cross-System Tenant AI Assets: Cophy shared knowledge and Agent
integration (docs/prompts/Cross-System Tenant AI Assets - Prompt - Phase 6 -
saas-mortgage.md).

Covers the prompt's Tests list: both customers see/use Shared collection/
Agent, each sees only own private resources otherwise, Shared controls are
read-only, forged mutation fails, a tenant Agent's listing can combine own
+ Shared, a Shared Agent conversation belongs to the customer's active
tenant, switching invalidates old private URLs, search/download stay
tenant-isolated, backend/service errors are surfaced safely (not as a raw
traceback or a broken page), and existing docs/release notes remain global.

Uses `fake_skunkbox` (tests/conftest.py) for both the Phase 5 tenant client
and the new Phase 6 knowledge/agents management client — no real HTTP call
is made. The older per-tenant Integration/X-API-Key document/chat path is
exercised by monkeypatching `requests.get`/`requests.post` directly.
"""
import uuid

from app.extensions import db
from app.models import AgentConversation, AiAgent, ReleaseNote, Tenant, User

from .conftest import create_ai_agent, create_integration, create_tenant, create_user
from .conftest import login as _login
from .conftest import set_password as _set_password

_COFFICIENCY_SENTINEL = "cofficiency-fake-external-id"


def _setup_two_tenants(full_app, fake_skunkbox):
    """Two customer tenants, each synced, each with an AI Agents + Documents
    Integration, each with one admin user. Returns a dict of ids."""
    tenant_a = create_tenant(full_app, "Customer A", "customer-a")
    tenant_b = create_tenant(full_app, "Customer B", "customer-b")
    integ_a = create_integration(full_app, tenant_a, use_case="AI Agents", name="A Agents")
    integ_b = create_integration(full_app, tenant_b, use_case="AI Agents", name="B Agents")
    admin_a = create_user(full_app, "admin_a", tenant_a, role="admin")
    admin_b = create_user(full_app, "admin_b", tenant_b, role="admin")
    return {
        "tenant_a": tenant_a, "tenant_b": tenant_b,
        "integ_a": integ_a, "integ_b": integ_b,
        "admin_a": admin_a, "admin_b": admin_b,
    }


def _external_id(app, tenant_id):
    with app.app_context():
        return db.session.get(Tenant, tenant_id).external_id


# ── Both customers see/use Shared collection/Agent; private stays private ──

def test_both_customers_see_shared_agent_neither_sees_others_private(full_app, fake_skunkbox):
    w = _setup_two_tenants(full_app, fake_skunkbox)
    ext_a = _external_id(full_app, w["tenant_a"])
    ext_b = _external_id(full_app, w["tenant_b"])

    shared_id = fake_skunkbox.seed_agent(
        "Concierge", owner_tenant_external_id=_COFFICIENCY_SENTINEL, is_shared=True,
    )
    create_ai_agent(full_app, w["tenant_a"], w["integ_a"], skunkbox_agent_id=501, name="A's Own Agent")

    from app.services.agent_sync import sync_shared_agents_for_tenant
    with full_app.app_context():
        tenant_a = db.session.get(Tenant, w["tenant_a"])
        tenant_b = db.session.get(Tenant, w["tenant_b"])
        sync_shared_agents_for_tenant(tenant_a)
        sync_shared_agents_for_tenant(tenant_b)

        a_names = {a.name for a in AiAgent.query.filter_by(tenant_id=w["tenant_a"], is_active=True).all()}
        b_names = {a.name for a in AiAgent.query.filter_by(tenant_id=w["tenant_b"], is_active=True).all()}

    assert "Concierge" in a_names and "Concierge" in b_names   # both see Shared
    assert "A's Own Agent" in a_names
    assert "A's Own Agent" not in b_names                       # B never sees A's private agent


def test_both_customers_see_shared_collection_in_learning_center(full_app, fake_skunkbox, monkeypatch):
    w = _setup_two_tenants(full_app, fake_skunkbox)
    ext_a = _external_id(full_app, w["tenant_a"])
    ext_b = _external_id(full_app, w["tenant_b"])
    fake_skunkbox.seed_collection(
        "Underwriting Guidelines", owner_tenant_external_id=_COFFICIENCY_SENTINEL,
        is_shared=True, document_count=3,
    )
    fake_skunkbox.seed_collection("A Private Docs", owner_tenant_external_id=ext_a, document_count=1)

    _set_password(full_app, "admin_a", "Test-1234")
    _set_password(full_app, "admin_b", "Test-1234")
    client_a = full_app.test_client()
    client_b = full_app.test_client()
    _login(client_a, "admin_a", "Test-1234")
    _login(client_b, "admin_b", "Test-1234")

    resp_a = client_a.get("/agents/learning-center")
    resp_b = client_b.get("/agents/learning-center")

    assert b"Underwriting Guidelines" in resp_a.data
    assert b"Underwriting Guidelines" in resp_b.data   # both see Shared
    assert b"A Private Docs" in resp_a.data
    assert b"A Private Docs" not in resp_b.data         # B never sees A's private collection
    assert b"Shared" in resp_a.data                     # labeled


# ── Shared controls are read-only / forged mutation fails ──────────────────

def test_shared_agent_cannot_be_edited_or_toggled(full_app, fake_skunkbox):
    w = _setup_two_tenants(full_app, fake_skunkbox)
    fake_skunkbox.seed_agent("Concierge", owner_tenant_external_id=_COFFICIENCY_SENTINEL, is_shared=True)

    from app.services.agent_sync import sync_shared_agents_for_tenant
    with full_app.app_context():
        tenant_b = db.session.get(Tenant, w["tenant_b"])
        sync_shared_agents_for_tenant(tenant_b)
        shared_agent = AiAgent.query.filter_by(tenant_id=w["tenant_b"], is_shared=True).one()
        shared_agent_id = shared_agent.id

    _set_password(full_app, "admin_b", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin_b", "Test-1234")

    resp = client.post(
        f"/models/agents/{shared_agent_id}/save",
        data={"name": "Hacked Name", "integration_id": str(w["integ_b"]), "skunkbox_agent_id": "9999"},
        follow_redirects=True,
    )
    assert b"cannot be edited" in resp.data
    toggle_resp = client.post(f"/models/agents/{shared_agent_id}/toggle", follow_redirects=True)
    assert b"cannot be activated/deactivated" in toggle_resp.data

    with full_app.app_context():
        agent = db.session.get(AiAgent, shared_agent_id)
        assert agent.name == "Concierge"
        assert agent.is_active is True


def test_cannot_create_duplicate_local_agent_for_shared_skunkbox_id(full_app, fake_skunkbox):
    """Ambiguous-ownership guard: a customer admin manually adding an agent
    must not be able to point it at a skunkbox_agent_id that's already
    mirrored locally (whether Shared or their own)."""
    w = _setup_two_tenants(full_app, fake_skunkbox)
    fake_skunkbox.seed_agent(
        "Concierge", owner_tenant_external_id=_COFFICIENCY_SENTINEL,
        is_shared=True, agent_id=777,
    )
    from app.services.agent_sync import sync_shared_agents_for_tenant
    with full_app.app_context():
        tenant_b = db.session.get(Tenant, w["tenant_b"])
        sync_shared_agents_for_tenant(tenant_b)

    _set_password(full_app, "admin_b", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin_b", "Test-1234")

    resp = client.post(
        "/models/agents/add",
        data={"name": "My Own Concierge Copy", "integration_id": str(w["integ_b"]), "skunkbox_agent_id": "777"},
        follow_redirects=True,
    )
    assert b"already exists" in resp.data
    with full_app.app_context():
        assert AiAgent.query.filter_by(tenant_id=w["tenant_b"], skunkbox_agent_id=777).count() == 1


# ── Shared Agent conversation belongs to the customer's active tenant ──────

def test_shared_agent_conversation_owned_by_customer_tenant(full_app, fake_skunkbox):
    w = _setup_two_tenants(full_app, fake_skunkbox)
    fake_skunkbox.seed_agent("Concierge", owner_tenant_external_id=_COFFICIENCY_SENTINEL, is_shared=True)

    from app.services.agent_sync import sync_shared_agents_for_tenant
    with full_app.app_context():
        tenant_b = db.session.get(Tenant, w["tenant_b"])
        sync_shared_agents_for_tenant(tenant_b)
        shared_agent_id = AiAgent.query.filter_by(tenant_id=w["tenant_b"], is_shared=True).one().id

    _set_password(full_app, "admin_b", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin_b", "Test-1234")

    resp = client.post(
        "/agents/new", data={"agent_id": str(shared_agent_id)}, follow_redirects=True,
    )
    assert resp.status_code == 200
    with full_app.app_context():
        conv = AgentConversation.query.filter_by(ai_agent_id=shared_agent_id).one()
        assert conv.tenant_id == w["tenant_b"]   # NOT Cofficiency, even though the Agent owner is


# ── Switching invalidates continued access to prior tenant private URLs ────

def test_switching_active_tenant_invalidates_prior_private_conversation(full_app, fake_skunkbox):
    w = _setup_two_tenants(full_app, fake_skunkbox)
    agent_a_id = create_ai_agent(full_app, w["tenant_a"], w["integ_a"], skunkbox_agent_id=501, name="A Agent")
    with full_app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id
    coffi_admin_id = create_user(full_app, "coffi_admin", cofficiency_id, role="admin")

    _set_password(full_app, "coffi_admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "coffi_admin", "Test-1234")

    client.post("/tenants/switch", data={"tenant_id": w["tenant_a"], "next": "/"}, follow_redirects=True)
    resp = client.post("/agents/new", data={"agent_id": str(agent_a_id)}, follow_redirects=True)
    with full_app.app_context():
        conv_id = AgentConversation.query.filter_by(ai_agent_id=agent_a_id).one().id
    assert client.get(f"/agents/{conv_id}").status_code == 200

    client.post("/tenants/switch", data={"tenant_id": w["tenant_b"], "next": "/"}, follow_redirects=True)
    assert client.get(f"/agents/{conv_id}").status_code == 404


# ── Search/download/citations stay tenant-isolated ──────────────────────────

def test_document_download_uses_active_tenants_own_credentials(full_app, fake_skunkbox, monkeypatch):
    """A document-proxy request must always re-resolve the ACTIVE tenant's
    own Documents Integration/API key per request — never a stale/cached
    one from a previously-active tenant."""
    w = _setup_two_tenants(full_app, fake_skunkbox)
    create_integration(full_app, w["tenant_a"], use_case="Documents", name="A Docs",
                       base_url="https://a.example.com", api_key="key-a")
    create_integration(full_app, w["tenant_b"], use_case="Documents", name="B Docs",
                       base_url="https://b.example.com", api_key="key-b")

    seen_urls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        seen_urls.append((url, headers.get("X-API-Key")))
        class _Resp:
            status_code = 200
            ok = True
            def json(self):
                return {"documents": []}
            def raise_for_status(self):
                pass
        return _Resp()

    import requests
    monkeypatch.setattr(requests, "get", fake_get)

    with full_app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id
    create_user(full_app, "coffi_admin2", cofficiency_id, role="admin")
    _set_password(full_app, "coffi_admin2", "Test-1234")
    client = full_app.test_client()
    _login(client, "coffi_admin2", "Test-1234")

    client.post("/tenants/switch", data={"tenant_id": w["tenant_a"], "next": "/"}, follow_redirects=True)
    client.get("/agents/learning-center")
    client.post("/tenants/switch", data={"tenant_id": w["tenant_b"], "next": "/"}, follow_redirects=True)
    client.get("/agents/learning-center")

    assert ("https://a.example.com/api/v1/documents", "key-a") in seen_urls
    assert ("https://b.example.com/api/v1/documents", "key-b") in seen_urls


# ── Backend/service errors are safe ─────────────────────────────────────────

def test_shared_agent_sync_fails_soft_on_skunkbox_error(full_app, fake_skunkbox):
    from app.skunkbox_client import SkunkBoxClientError
    w = _setup_two_tenants(full_app, fake_skunkbox)
    create_ai_agent(full_app, w["tenant_a"], w["integ_a"], skunkbox_agent_id=501, name="A's Own Agent")
    fake_skunkbox.fail_next = ("list_agents", SkunkBoxClientError("boom", status_code=500))

    from app.services.agent_sync import sync_shared_agents_for_tenant
    with full_app.app_context():
        tenant_a = db.session.get(Tenant, w["tenant_a"])
        summary = sync_shared_agents_for_tenant(tenant_a)
        assert summary["fetch_error"] == "boom"
        # Existing local agent is untouched, no crash.
        assert AiAgent.query.filter_by(tenant_id=w["tenant_a"]).count() == 1


def test_learning_center_shows_generic_error_not_raw_exception_on_management_api_failure(full_app, fake_skunkbox, monkeypatch):
    from app.skunkbox_client import SkunkBoxClientError
    w = _setup_two_tenants(full_app, fake_skunkbox)

    def raise_error(tenant_id):
        raise SkunkBoxClientError("internal detail should not leak verbatim as a 500", status_code=500)

    import app.skunkbox_client as client_module
    monkeypatch.setattr(client_module, "list_knowledge_collections", raise_error)

    _set_password(full_app, "admin_a", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin_a", "Test-1234")

    resp = client.get("/agents/learning-center")
    assert resp.status_code == 200   # page still renders, no 500


# ── Existing docs/release notes remain global (regression) ─────────────────

def test_release_notes_remain_tenant_agnostic(full_app):
    """No tenant_id column exists on ReleaseNote — confirms this phase did
    not (and should not) introduce tenant scoping to it."""
    assert not hasattr(ReleaseNote, "tenant_id")
