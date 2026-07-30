"""Tenant Completion Phase 5: customer Agent/knowledge configuration."""
from app.extensions import db
from app.models import AiAgent, ApiRequestLog, Tenant, User, UserActivityLog
from app.skunkbox_client import SkunkBoxClientError

from .conftest import create_integration, create_tenant, create_user, login, set_password


def _customer(full_app, fake, suffix="a"):
    tenant_id = create_tenant(full_app, f"Customer {suffix.upper()}", f"customer-{suffix}")
    user_id = create_user(full_app, f"agent_admin_{suffix}", tenant_id, role="admin")
    integration_id = create_integration(full_app, tenant_id)
    with full_app.app_context():
        tenant = db.session.get(Tenant, tenant_id)
        external_id = tenant.external_id
    own_collection = fake.seed_collection("Private Policies", external_id)
    shared_collection = fake.seed_collection("Mortgage Standards", "cofficiency-remote", is_shared=True)
    set_password(full_app, f"agent_admin_{suffix}", "Test-1234")
    client = full_app.test_client()
    login(client, f"agent_admin_{suffix}", "Test-1234")
    return client, tenant_id, user_id, integration_id, external_id, own_collection, shared_collection


def test_customer_creates_agent_with_own_and_shared_collections(full_app, fake_skunkbox):
    client, tenant_id, _, integration_id, external_id, own_id, shared_id = _customer(
        full_app, fake_skunkbox
    )
    response = client.post("/models/agents/add", data={
        "name": "Policy Assistant", "role_title": "Policy Expert",
        "description": "Answers policy questions", "system_prompt": "Cite the policy.",
        "model_id": "1", "integration_id": str(integration_id),
        "collection_ids": [str(own_id), str(shared_id)],
    }, follow_redirects=False)

    assert response.status_code == 302
    remote = next(iter(fake_skunkbox.agents.values()))
    assert remote["_owner"] == external_id
    assert remote["is_shared"] is False
    assert remote["collection_ids"] == [own_id, shared_id]
    with full_app.app_context():
        pointer = AiAgent.query.filter_by(tenant_id=tenant_id, skunkbox_agent_id=remote["id"]).one()
        assert pointer.is_shared is False
        activity = UserActivityLog.query.filter_by(
            tenant_id=tenant_id, action="agent.created"
        ).one()
        assert activity.user_id is not None


def test_agent_edit_rejects_cross_tenant_collection_and_reports_partial_success(
    full_app, fake_skunkbox
):
    client, tenant_id, _, integration_id, external_id, own_id, _ = _customer(full_app, fake_skunkbox)
    foreign_external = "foreign-tenant"
    foreign_collection = fake_skunkbox.seed_collection("Foreign", foreign_external)
    remote_id = fake_skunkbox.seed_agent("Original", external_id, collection_ids=[own_id])
    with full_app.app_context():
        pointer = AiAgent(
            tenant_id=tenant_id, name="Original", integration_id=integration_id,
            skunkbox_agent_id=remote_id, is_shared=False,
        )
        db.session.add(pointer)
        db.session.commit()
        pointer_id = pointer.id

    response = client.post(f"/models/agents/{pointer_id}/save", data={
        "name": "Updated First", "collection_ids": [str(foreign_collection)]
    }, follow_redirects=True)

    assert b"not fully saved" in response.data
    assert fake_skunkbox.agents[remote_id]["name"] == "Updated First"
    assert fake_skunkbox.agents[remote_id]["collection_ids"] == [own_id]


def test_shared_agent_is_read_only_and_has_no_customer_mutation_controls(full_app, fake_skunkbox):
    client, tenant_id, _, integration_id, _, _, _ = _customer(full_app, fake_skunkbox)
    shared_id = fake_skunkbox.seed_agent("Cofficiency Agent", "cofficiency-remote", is_shared=True)
    client.get("/models/")
    with full_app.app_context():
        pointer = AiAgent.query.filter_by(
            tenant_id=tenant_id, skunkbox_agent_id=shared_id
        ).one()
        pointer_id = pointer.id

    page = client.get(f"/models/agents/{pointer_id}/edit")
    assert page.status_code == 200
    assert b"Shared Agent" in page.data and b"Read-only" in page.data
    assert b"Save Agent" not in page.data
    denied = client.post(f"/models/agents/{pointer_id}/save", data={"name": "Hijacked"})
    assert denied.status_code == 302
    assert fake_skunkbox.agents[shared_id]["name"] == "Cofficiency Agent"


def test_switching_tenants_invalidates_open_agent_edit_url(full_app, fake_skunkbox):
    tenant_a = create_tenant(full_app, "Switch A", "switch-a")
    tenant_b = create_tenant(full_app, "Switch B", "switch-b")
    integration_a = create_integration(full_app, tenant_a)
    with full_app.app_context():
        a = db.session.get(Tenant, tenant_a)
        b = db.session.get(Tenant, tenant_b)
        admin = User.query.filter_by(username="admin").one()
        admin.last_active_tenant_id = tenant_a
        remote_id = fake_skunkbox.seed_agent("A Agent", a.external_id)
        pointer = AiAgent(
            tenant_id=tenant_a, name="A Agent", integration_id=integration_a,
            skunkbox_agent_id=remote_id,
        )
        db.session.add(pointer)
        db.session.commit()
        pointer_id = pointer.id
        tenant_b_id = b.id
    set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    login(client, "admin", "Test-1234")
    assert client.get(f"/models/agents/{pointer_id}/edit").status_code == 200
    client.post("/tenants/switch", data={"tenant_id": tenant_b_id, "next": "/"})
    assert client.get(f"/models/agents/{pointer_id}/edit").status_code == 404


def test_management_client_records_safe_correlation_audit(full_app, monkeypatch):
    import app.skunkbox_client as client_module

    class Response:
        status_code = 200
        headers = {"X-Request-ID": "skunk-request-42"}
        def json(self):
            return {"agents": []}

    seen = {}
    def request(method, url, headers, json, params, timeout):
        seen.update(headers)
        return Response()

    monkeypatch.setattr(client_module.requests, "request", request)
    with full_app.app_context():
        tenant = Tenant.query.filter_by(slug="advantagefirst").one()
        full_app.config["SKUNKBOX_SERVICE_SECRET"] = "do-not-store-this-secret"
        client_module.list_agents(tenant.external_id)
        row = ApiRequestLog.query.filter_by(
            integration_name="skunkBOX Management API"
        ).order_by(ApiRequestLog.id.desc()).first()
        assert row.tenant_id == tenant.id
        assert row.endpoint == "/api/v1/management/agents"
        assert row.operation == "agents"
        assert row.status_code == 200
        assert row.correlation_id == "skunk-request-42"
        assert "do-not-store-this-secret" not in repr(row.__dict__)
        assert seen["X-Service-Secret"] == "do-not-store-this-secret"


def test_agent_page_handles_backend_timeout_without_exposing_secret(full_app, fake_skunkbox):
    client, _, _, _, _, _, _ = _customer(full_app, fake_skunkbox)
    fake_skunkbox.fail_next = (
        "list_agents", SkunkBoxClientError("timeout while using super-secret"),
    )
    response = client.get("/models/")
    assert response.status_code == 200
    assert b"temporarily unavailable" in response.data
    assert b"super-secret" not in response.data


def test_agent_creation_requires_csrf_when_protection_enabled(full_app, fake_skunkbox):
    client, _, _, integration_id, _, _, _ = _customer(full_app, fake_skunkbox, "csrf")
    full_app.config["WTF_CSRF_ENABLED"] = True
    try:
        response = client.post("/models/agents/add", data={
            "name": "Cross-site Agent", "integration_id": str(integration_id),
        })
        assert response.status_code == 302
        assert fake_skunkbox.agents == {}
    finally:
        full_app.config["WTF_CSRF_ENABLED"] = False
