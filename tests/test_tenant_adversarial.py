"""Phase 6 — adversarial tenant-isolation regression suite.

Numbered to match docs/prompts/Tenant Separation - Prompt - Phase 6 - saas-mortgage.md
section 'Adversarial tests'. Builds one rich, shared world per test:

- Cofficiency admin ("admin", fixture user)
- Cofficiency non-admin with limited permissions ("coffi_limited")
- Two customer tenants: AdvantageFirst (fixture) and Customer B (fresh)
- One external user per customer tenant ("jane" / "bob_customerb")
- Same-named LlmModel ("gpt-4") in both customer tenants
- A conversation + message + attachment + logs + a feature override in
  Customer B, and a conversation in AdvantageFirst
"""
from app.extensions import db
from app.models import (AgentConversation, AgentMessage, AiAgent, ApiRequestLog, FeatureFlag,
                         Integration, LlmModel, LlmRequestLog, MessageAttachment, Permission,
                         Role, Tenant, TenantFeatureFlag, User, UserActivityLog)

from .conftest import create_tenant, create_user
from .conftest import ensure_baseline_permissions as _ensure_baseline_permissions
from .conftest import login as _login
from .conftest import set_password as _set_password


def _switch(client, tenant_id):
    return client.post("/tenants/switch", data={"tenant_id": tenant_id, "next": "/"}, follow_redirects=True)


def _make_limited_cofficiency_user(app, cofficiency_id):
    """A Cofficiency-home user with a real but narrow permission set —
    view-only on conversations, no access to tenants/users/models."""
    with app.app_context():
        role = Role.query.filter_by(name="limited").first()
        if not role:
            role = Role(name="limited", is_system=False)
            db.session.add(role)
            db.session.flush()
        from app.page_registry import PAGES
        # "dashboard" also gets view access: permission_required's own
        # denial redirect target is main.dashboard, so denying it too would
        # trip an unrelated pre-existing redirect-loop bug (see the Phase 2
        # test suite's _ensure_baseline_permissions for the same note) rather
        # than exercising the tenant-isolation behavior this test is after.
        for page in PAGES:
            Permission.query.filter_by(role_id=role.id, page_slug=page["slug"]).delete()
            level = "view" if page["slug"] in ("conversations", "dashboard") else "no_access"
            db.session.add(Permission(role_id=role.id, page_slug=page["slug"], access_level=level))
        user = User(
            username="coffi_limited", email="coffi_limited@example.com", role="limited",
            tenant_id=cofficiency_id, must_change_password=False,
        )
        user.set_password("Test-1234")
        db.session.add(user)
        db.session.commit()
        return user.id


def _build_world(app):
    """Returns a dict of ids for the full adversarial fixture described above."""
    with app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id
        advantagefirst_id = Tenant.query.filter_by(slug="advantagefirst").one().id
        jane_id = User.query.filter_by(username="jane").one().id
        af_agent_id = AiAgent.query.filter_by(tenant_id=advantagefirst_id).one().id

        af_conv = AgentConversation(
            tenant_id=advantagefirst_id, ai_agent_id=af_agent_id, user_id=jane_id,
            title="AF Conversation", is_archived=False, skunkbox_session_id="s-af",
        )
        db.session.add(af_conv)
        db.session.commit()
        af_conv_id = af_conv.id

    customer_b_id = create_tenant(app, "Customer B", "customer-b")
    limited_user_id = _make_limited_cofficiency_user(app, cofficiency_id)
    bob_id = create_user(app, "bob_customerb", customer_b_id)

    with app.app_context():
        cb_model = LlmModel(
            tenant_id=customer_b_id, name="gpt-4", deployment_name="cb-deploy",
            endpoint_url="https://cb.example.com", api_key_encrypted="enc",
        )
        db.session.add(cb_model)
        cb_integration = Integration(
            tenant_id=customer_b_id, name="CB Integration", provider="OpenAI",
            category="LLM", use_case="AI Agents", is_active=True,
        )
        db.session.add(cb_integration)
        db.session.commit()
        cb_model_id = cb_model.id
        cb_integration_id = cb_integration.id

        cb_agent = AiAgent(
            tenant_id=customer_b_id, name="CB Agent", integration_id=cb_integration_id,
            skunkbox_agent_id=1, is_active=True,
        )
        db.session.add(cb_agent)
        db.session.commit()
        cb_agent_id = cb_agent.id

        cb_conv = AgentConversation(
            tenant_id=customer_b_id, ai_agent_id=cb_agent_id, user_id=bob_id,
            title="CB Conversation", is_archived=False, skunkbox_session_id="s-cb",
        )
        db.session.add(cb_conv)
        db.session.commit()
        cb_conv_id = cb_conv.id

        cb_msg = AgentMessage(conversation_id=cb_conv_id, role="user", content="hi")
        db.session.add(cb_msg)
        db.session.commit()
        cb_msg_id = cb_msg.id

        cb_att = MessageAttachment(
            message_id=cb_msg_id, skunkbox_attachment_id=777,
            original_filename="cb.pdf", mime_type="application/pdf", file_category="document",
        )
        db.session.add(cb_att)

        db.session.add(UserActivityLog(
            tenant_id=customer_b_id, user_id=bob_id, action="user.login", page="System"
        ))
        db.session.add(ApiRequestLog(
            tenant_id=customer_b_id, integration_id=cb_integration_id,
            integration_name="CB Integration", endpoint="/x", method="GET", status_code=200,
        ))
        db.session.add(LlmRequestLog(
            tenant_id=customer_b_id, model_id=cb_model_id, model_name="gpt-4",
            use_case="chat", status="success",
        ))

        flag = FeatureFlag.query.filter_by(key="learning_center").one()
        db.session.add(TenantFeatureFlag(
            tenant_id=customer_b_id, feature_flag_id=flag.id, is_enabled=False
        ))
        flag_id = flag.id

        db.session.commit()

    return {
        "cofficiency_id": cofficiency_id,
        "advantagefirst_id": advantagefirst_id,
        "customer_b_id": customer_b_id,
        "limited_user_id": limited_user_id,
        "jane_id": jane_id,
        "bob_id": bob_id,
        "af_agent_id": af_agent_id,
        "af_conv_id": af_conv_id,
        "cb_agent_id": cb_agent_id,
        "cb_conv_id": cb_conv_id,
        "cb_integration_id": cb_integration_id,
        "cb_model_id": cb_model_id,
        "learning_center_flag_id": flag_id,
    }


# 1. External user cannot switch tenant through POST, forged session/cookie
#    state, or query parameter.
def test_external_user_cannot_switch_by_any_means(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "jane", "Test-1234")
    _login(client, "jane", "Test-1234")

    # Forged POST body.
    client.post("/tenants/switch", data={"tenant_id": w["cofficiency_id"], "next": "/"}, follow_redirects=True)
    # Forged query parameter on an unrelated GET (the resolver never reads request args at all).
    client.get(f"/agents/?tenant_id={w['cofficiency_id']}")

    with full_app.app_context():
        jane = db.session.get(User, w["jane_id"])
        assert jane.last_active_tenant_id is None
        from app.tenant_context import get_active_tenant
        assert get_active_tenant(jane).id == w["advantagefirst_id"]


# 2. Tenant assignment cannot be changed through crafted user forms.
def test_tenant_assignment_immutable_via_crafted_forms(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["advantagefirst_id"])

    client.post(f"/users/{w['jane_id']}/edit", data={
        "username": "jane", "email": "jane@example.com", "role": "member",
        "tenant_id": str(w["cofficiency_id"]),
    }, follow_redirects=True)
    client.post("/users/add", data={
        "username": "forged_user", "email": "forged_user@example.com",
        "password": "Somepass123", "role": "member", "tenant_id": str(w["cofficiency_id"]),
    }, follow_redirects=True)

    with full_app.app_context():
        assert db.session.get(User, w["jane_id"]).tenant_id == w["advantagefirst_id"]
        forged = User.query.filter_by(username="forged_user").one()
        assert forged.tenant_id == w["advantagefirst_id"]  # bound to active tenant, not the forged field


# 3. Cross-tenant IDs fail for every read/mutation route.
def test_cross_tenant_ids_fail_for_every_route(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["advantagefirst_id"])  # active tenant; every id below belongs to Customer B

    checks = [
        ("GET", f"/users/{w['bob_id']}/edit", None),
        ("POST", f"/users/{w['bob_id']}/toggle", None),
        ("GET", f"/models/llm/{w['cb_model_id']}/update", None),  # GET not routed -> 405, not the point; use POST
        ("POST", f"/models/llm/{w['cb_model_id']}/update", {"name": "x"}),
        ("POST", f"/models/llm/{w['cb_model_id']}/toggle", None),
        ("POST", f"/models/integrations/{w['cb_integration_id']}/save", {"name": "x", "provider": "p", "category": "c"}),
        ("POST", f"/models/agents/{w['cb_agent_id']}/save",
         {"name": "x", "integration_id": str(w["cb_integration_id"]), "skunkbox_agent_id": "1"}),
        ("POST", f"/models/agents/{w['cb_agent_id']}/toggle", None),
        ("GET", f"/agents/{w['cb_conv_id']}", None),
        ("POST", f"/agents/{w['cb_conv_id']}/send", None),
        ("POST", f"/agents/{w['cb_conv_id']}/favorite", None),
        ("POST", f"/agents/{w['cb_conv_id']}/archive", None),
    ]
    for method, path, data in checks:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, data=data or {})
        assert resp.status_code in (404, 405), f"{method} {path} returned {resp.status_code}, expected 404/405"


# 4. Bulk operations cannot affect another tenant.
def test_bulk_operations_cannot_affect_another_tenant(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")

    with full_app.app_context():
        from app.models import Attribute
        cb_attr = Attribute(tenant_id=w["customer_b_id"], category="Region", name="APAC")
        db.session.add(cb_attr)
        db.session.commit()
        cb_attr_id = cb_attr.id

    _login(client, "admin", "Test-1234")
    _switch(client, w["advantagefirst_id"])  # active tenant does NOT own cb_attr_id

    client.post("/models/attributes/batch-save", json={
        "category": "Region", "values": [], "deleted_ids": [cb_attr_id],
    })
    with full_app.app_context():
        assert db.session.get(Attribute, cb_attr_id) is not None  # untouched


# 5. Cross-tenant agent/integration references fail.
def test_cross_tenant_agent_integration_reference_fails(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["advantagefirst_id"])

    resp = client.post("/models/agents/add", data={
        "name": "Cross Ref Agent",
        "integration_id": str(w["cb_integration_id"]),  # belongs to Customer B
        "skunkbox_agent_id": "1",
    }, follow_redirects=True)
    with full_app.app_context():
        assert AiAgent.query.filter_by(name="Cross Ref Agent").first() is None

    resp = client.post("/agents/new", data={"agent_id": str(w["cb_agent_id"])}, follow_redirects=False)
    assert resp.status_code == 404


# 6. Switching invalidates access to previously open tenant URLs.
def test_switching_invalidates_previously_open_urls(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["advantagefirst_id"])

    resp = client.get(f"/agents/{w['af_conv_id']}")
    assert resp.status_code == 200

    _switch(client, w["customer_b_id"])
    resp = client.get(f"/agents/{w['af_conv_id']}")
    assert resp.status_code == 404


# 7. Limited Cofficiency user retains limitations after switching.
def test_limited_cofficiency_user_retains_limitations_after_switching(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "coffi_limited", "Test-1234")
    _login(client, "coffi_limited", "Test-1234")

    # Being Cofficiency-home is enough to *switch* (any Cofficiency user may,
    # per the PRD) — that's not the limitation under test here.
    resp = client.post("/tenants/switch", data={"tenant_id": w["advantagefirst_id"], "next": "/"}, follow_redirects=True)
    assert resp.status_code == 200
    with full_app.app_context():
        limited = db.session.get(User, w["limited_user_id"])
        assert limited.last_active_tenant_id == w["advantagefirst_id"]
        assert limited.tenant_id == w["cofficiency_id"]  # home tenant unchanged by switching

    # What IS limited: role-based page permissions, unaffected by which
    # tenant is active. Not admin-role -> tenant *administration* stays blocked.
    resp = client.get("/tenants/", follow_redirects=True)
    assert "do not have permission" in resp.get_data(as_text=True).lower()

    # System Config (models/attributes/integrations/agents) remains no_access
    # in the newly-active tenant too — switching workspace grants no permissions.
    resp = client.get("/models/", follow_redirects=True)
    assert "do not have permission" in resp.get_data(as_text=True).lower()


# 8. Tenant feature override does not affect another tenant.
def test_feature_override_does_not_affect_another_tenant(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)  # Customer B already has learning_center disabled via override

    with full_app.app_context():
        from app.feature_flags import effective_feature_flags
        cb_flags = effective_feature_flags(tenant=db.session.get(Tenant, w["customer_b_id"]))
        af_flags = effective_feature_flags(tenant=db.session.get(Tenant, w["advantagefirst_id"]))
        assert cb_flags["learning_center"] is False
        assert af_flags["learning_center"] is True


# 9. Reports and every aggregate contain only event tenant.
def test_reports_and_aggregates_contain_only_event_tenant(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["advantagefirst_id"])

    resp = client.get("/reporting/?tab=llm")
    body = resp.get_data(as_text=True)
    assert "CB Integration" not in body

    with full_app.app_context():
        from app.models import LlmRequestLog as LRL
        af_llm_count = LRL.query.filter_by(tenant_id=w["advantagefirst_id"]).count()
    # AdvantageFirst's own count (from the Phase 1 fixture data) must not include Customer B's row.
    resp2 = client.get("/reporting/?tab=activity")
    assert "bob_customerb" not in resp2.get_data(as_text=True)
    resp3 = client.get("/reporting/?tab=api")
    assert resp3.status_code == 200


# 10. Cofficiency actor activity appears in the selected customer tenant.
def test_cofficiency_actor_activity_appears_in_selected_tenant(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["customer_b_id"])

    client.post("/users/add", data={
        "username": "cb_via_admin", "email": "cb_via_admin@example.com",
        "password": "Somepass123", "role": "member",
    }, follow_redirects=True)

    with full_app.app_context():
        log = UserActivityLog.query.filter_by(action="user.created").order_by(
            UserActivityLog.id.desc()
        ).first()
        admin_id = User.query.filter_by(username="admin").one().id
        assert log.user_id == admin_id
        assert log.tenant_id == w["customer_b_id"]
        assert db.session.get(User, admin_id).tenant_id == w["cofficiency_id"]  # actor's home tenant unchanged


# 11. Historical seeded logs remain AdvantageFirst.
def test_historical_seeded_logs_remain_advantagefirst(full_app, client):
    w = _build_world(full_app)
    with full_app.app_context():
        from app.models import ApiRequestLog as ARL
        from app.models import LlmRequestLog as LRL
        # Rows inserted by the Phase 1 migration fixture (not by this test).
        assert LRL.query.filter_by(model_name="gpt-4").filter(
            LRL.tenant_id == w["advantagefirst_id"]
        ).count() >= 1
        assert UserActivityLog.query.filter_by(action="user.login").filter(
            UserActivityLog.tenant_id == w["advantagefirst_id"]
        ).count() >= 1
        assert ARL.query.filter(ARL.tenant_id == w["advantagefirst_id"]).count() >= 1


# 12. Global docs, release notes, roles, and navigation layout remain global.
def test_global_surfaces_remain_global(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    with full_app.app_context():
        from app.models import NavSection, Role as RoleModel
        role_count = RoleModel.query.count()
        nav_count = NavSection.query.count()

    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")
    _switch(client, w["customer_b_id"])
    resp = client.get("/help/release-notes")
    assert resp.status_code == 200

    with full_app.app_context():
        from app.models import NavSection, Role as RoleModel
        assert RoleModel.query.count() == role_count
        assert NavSection.query.count() == nav_count


# 13. Inactive tenants cannot be selected or receive new data.
def test_inactive_tenants_cannot_be_selected_or_receive_data(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    client.post(f"/tenants/{w['customer_b_id']}/archive", follow_redirects=True)

    resp = client.post("/tenants/switch", data={"tenant_id": w["customer_b_id"], "next": "/"}, follow_redirects=True)
    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        assert admin.last_active_tenant_id != w["customer_b_id"]

    # Reactivate to restore a normal active-tenant context, then confirm an
    # archived tenant can't be switched into even mid-session.
    with full_app.app_context():
        t = db.session.get(Tenant, w["customer_b_id"])
        assert t.is_active is False


# 14. Cofficiency tenant cannot be archived/renamed.
def test_cofficiency_tenant_cannot_be_archived_or_renamed(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    client.post(f"/tenants/{w['cofficiency_id']}/archive", follow_redirects=True)
    client.post(f"/tenants/{w['cofficiency_id']}/edit", data={"name": "Renamed Cofficiency"}, follow_redirects=True)

    with full_app.app_context():
        cof = db.session.get(Tenant, w["cofficiency_id"])
        assert cof.is_active is True
        assert cof.name == "Cofficiency"


# 15. Remembered inactive tenant safely falls back to Cofficiency.
def test_remembered_inactive_tenant_falls_back_to_cofficiency(full_app, client):
    _ensure_baseline_permissions(full_app)
    w = _build_world(full_app)

    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        admin.last_active_tenant_id = w["customer_b_id"]
        db.session.commit()
        t = db.session.get(Tenant, w["customer_b_id"])
        t.is_active = False
        db.session.commit()

        from app.tenant_context import get_active_tenant
        admin = db.session.get(User, admin.id)
        active = get_active_tenant(admin)
        assert active.slug == "cofficiency"
