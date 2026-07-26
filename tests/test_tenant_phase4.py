"""Tests for Phase 4 — Tenant-Isolated Configuration and Feature Flags.

Numbered to match docs/prompts/Tenant Separation - Prompt - Phase 4 - saas-mortgage.md
section 'Tests'. Uses three tenants: Cofficiency, AdvantageFirst (Phase 1's
historical fixture tenant), and a fresh "Customer B" tenant.
"""
from app.extensions import db
from app.models import (AgentConversation, AiAgent, Attribute, FeatureFlag, Integration,
                         LlmModel, Role, Tenant, TenantFeatureFlag, User)

from .conftest import create_tenant, create_user
from .conftest import login as _login
from .conftest import set_password as _set_password


def _tenant_id(app, slug):
    with app.app_context():
        return Tenant.query.filter_by(slug=slug).one().id


def _switch(client, tenant_id):
    return client.post("/tenants/switch", data={"tenant_id": tenant_id, "next": "/"}, follow_redirects=True)


def _make_integration(app, tenant_id, name="OpenAI Prod", use_case="AI Agents"):
    with app.app_context():
        integ = Integration(
            tenant_id=tenant_id, name=name, provider="OpenAI", category="LLM",
            use_case=use_case, is_active=True,
        )
        db.session.add(integ)
        db.session.commit()
        return integ.id


def _make_agent(app, tenant_id, integration_id, name="Helper", skunkbox_agent_id=None):
    """`skunkbox_agent_id` defaults to a value unique within `tenant_id` —
    the legacy fixture data already seeds a skunkbox_agent_id=1 'Helper'
    agent under AdvantageFirst, and (tenant_id, skunkbox_agent_id) is
    unique (Phase 6: no ambiguous duplicate local ownership of one skunkBOX
    agent), so a caller creating a second agent for the same tenant must
    not collide with it."""
    with app.app_context():
        if skunkbox_agent_id is None:
            existing_ids = {
                row[0] for row in
                db.session.query(AiAgent.skunkbox_agent_id).filter_by(tenant_id=tenant_id).all()
            }
            skunkbox_agent_id = next(i for i in range(1, 1000) if i not in existing_ids)
        agent = AiAgent(
            tenant_id=tenant_id, name=name, integration_id=integration_id,
            skunkbox_agent_id=skunkbox_agent_id, is_active=True,
        )
        db.session.add(agent)
        db.session.commit()
        return agent.id


def _make_conversation(app, agent_id, tenant_id, user_id, title="Conv"):
    with app.app_context():
        conv = AgentConversation(
            tenant_id=tenant_id, ai_agent_id=agent_id, user_id=user_id,
            title=title, is_archived=False,
        )
        db.session.add(conv)
        db.session.commit()
        return conv.id


# 1. Same model/attribute/integration name is allowed in different tenants.
def test_same_name_allowed_across_tenants(full_app, client):
    # AdvantageFirst already has a "gpt-4" model from the Phase 1 fixture data,
    # so this only needs to prove a *different* tenant can reuse that same name.
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    resp = client.post("/models/llm/add", data={
        "name": "gpt-4", "deployment_name": "gpt-4-deploy-b",
        "endpoint_url": "https://b.example.com", "api_key": "key-b",
    }, follow_redirects=True)
    assert resp.status_code == 200

    with full_app.app_context():
        rows = LlmModel.query.filter_by(name="gpt-4").all()
        assert len(rows) == 2
        assert {r.tenant_id for r in rows} == {advantagefirst_id, customer_b_id}


# 2. Duplicate within one tenant is rejected.
def test_duplicate_within_one_tenant_rejected(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    client.post("/models/llm/add", data={
        "name": "gpt-4", "deployment_name": "d1", "endpoint_url": "https://x.example.com", "api_key": "k",
    }, follow_redirects=True)
    resp = client.post("/models/llm/add", data={
        "name": "gpt-4", "deployment_name": "d2", "endpoint_url": "https://y.example.com", "api_key": "k",
    }, follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "already exists" in body.lower()

    with full_app.app_context():
        assert LlmModel.query.filter_by(tenant_id=customer_b_id, name="gpt-4").count() == 1


# 3. Lists expose only active-tenant records.
def test_lists_expose_only_active_tenant_records(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        db.session.add(Attribute(tenant_id=customer_b_id, category="Region", name="EMEA"))
        db.session.commit()

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get("/models/")
    body = resp.get_data(as_text=True)
    assert "EMEA" not in body
    assert "gpt-4" in body  # AdvantageFirst's historical fixture model

    _switch(client, customer_b_id)
    resp = client.get("/models/")
    body = resp.get_data(as_text=True)
    assert "EMEA" in body
    assert "gpt-4" not in body


# 4. Creates bind active tenant despite forged input.
def test_create_binds_active_tenant_despite_forged_input(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    client.post("/models/llm/add", data={
        "name": "forged-test-model", "deployment_name": "d",
        "endpoint_url": "https://x.example.com", "api_key": "k",
        "tenant_id": "999999",
    }, follow_redirects=True)

    with full_app.app_context():
        model = LlmModel.query.filter_by(name="forged-test-model").one()
        assert model.tenant_id == customer_b_id


# 5. Cross-tenant update/toggle/delete/batch IDs are rejected.
def test_cross_tenant_update_toggle_batch_rejected(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        af_model = LlmModel.query.filter_by(tenant_id=advantagefirst_id).first()
        af_model_id = af_model.id
        af_attr = Attribute(tenant_id=advantagefirst_id, category="Region", name="APAC")
        db.session.add(af_attr)
        db.session.commit()
        af_attr_id = af_attr.id

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)  # active tenant is now Customer B, target belongs to AdvantageFirst

    resp = client.post(f"/models/llm/{af_model_id}/update", data={"name": "hacked"}, follow_redirects=False)
    assert resp.status_code == 404

    resp = client.post(f"/models/llm/{af_model_id}/toggle", follow_redirects=False)
    assert resp.status_code == 404

    # Cross-tenant batch delete: attribute belongs to AdvantageFirst, active tenant is Customer B.
    resp = client.post(
        "/models/attributes/batch-save",
        json={"category": "Region", "values": [], "deleted_ids": [af_attr_id]},
    )
    assert resp.status_code == 200
    with full_app.app_context():
        assert db.session.get(Attribute, af_attr_id) is not None  # not deleted
        assert db.session.get(LlmModel, af_model_id).name != "hacked"


# 6. Default-model updates do not affect another tenant.
def test_default_model_update_scoped_to_active_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    client.post("/models/llm/add", data={
        "name": "cb-model-1", "deployment_name": "d1", "endpoint_url": "https://x.example.com",
        "api_key": "k", "is_default": "1",
    }, follow_redirects=True)
    client.post("/models/llm/add", data={
        "name": "cb-model-2", "deployment_name": "d2", "endpoint_url": "https://y.example.com",
        "api_key": "k", "is_default": "1",
    }, follow_redirects=True)

    with full_app.app_context():
        cb1 = LlmModel.query.filter_by(tenant_id=customer_b_id, name="cb-model-1").one()
        cb2 = LlmModel.query.filter_by(tenant_id=customer_b_id, name="cb-model-2").one()
        assert cb1.is_default is False
        assert cb2.is_default is True

        af_model = LlmModel.query.filter_by(tenant_id=advantagefirst_id).first()
        assert af_model.is_default is True  # AdvantageFirst's own default untouched by Customer B's changes


# 7. Agent cannot reference another tenant's integration.
def test_agent_cannot_reference_another_tenants_integration(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    af_integration_id = _make_integration(full_app, advantagefirst_id, name="AF Integration")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    resp = client.post("/models/agents/add", data={
        "name": "Cross Tenant Agent",
        "integration_id": str(af_integration_id),
        "skunkbox_agent_id": "1",
    }, follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "belongs to the active tenant" in body.lower() or "active tenant" in body.lower()

    with full_app.app_context():
        assert AiAgent.query.filter_by(name="Cross Tenant Agent").first() is None


# 8. Agent deactivation cannot archive another tenant's conversations.
def test_agent_deactivation_does_not_archive_other_tenant_conversations(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        admin_id = User.query.filter_by(username="admin").one().id

    cb_integration_id = _make_integration(full_app, customer_b_id, name="CB Integration")
    cb_agent_id = _make_agent(full_app, customer_b_id, cb_integration_id, name="CB Agent")
    af_integration_id = _make_integration(full_app, advantagefirst_id, name="AF Integration 2")
    af_agent_id = _make_agent(full_app, advantagefirst_id, af_integration_id, name="AF Agent")
    af_conv_id = _make_conversation(full_app, af_agent_id, advantagefirst_id, admin_id, title="AF Conversation")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    client.post(f"/models/agents/{cb_agent_id}/toggle", follow_redirects=True)  # deactivate Customer B's own agent

    with full_app.app_context():
        af_conv = db.session.get(AgentConversation, af_conv_id)
        assert af_conv.is_archived is False  # untouched — belongs to a different tenant's agent


# 9. Feature state inherits enabled global default.
def test_feature_state_inherits_enabled_global_default(full_app, client):
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    with full_app.app_context():
        from app.feature_flags import effective_feature_flags
        flags = effective_feature_flags(tenant=db.session.get(Tenant, customer_b_id))
        assert flags.get("conversations") is True  # global default is enabled, no override yet


# 10. Tenant override changes only selected tenant.
def test_tenant_override_changes_only_selected_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        flag = FeatureFlag.query.filter_by(key="learning_center").one()
        flag_id = flag.id

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    client.post(f"/models/flags/{flag_id}/toggle", data={}, follow_redirects=True)  # unchecked -> disabled

    with full_app.app_context():
        from app.feature_flags import effective_feature_flags
        cb_flags = effective_feature_flags(tenant=db.session.get(Tenant, customer_b_id))
        af_flags = effective_feature_flags(tenant=db.session.get(Tenant, advantagefirst_id))
        assert cb_flags["learning_center"] is False
        assert af_flags["learning_center"] is True  # unaffected

    # Reset removes the override and reverts to the global default.
    client.post(f"/models/flags/{flag_id}/reset", follow_redirects=True)
    with full_app.app_context():
        assert TenantFeatureFlag.query.filter_by(
            tenant_id=customer_b_id, feature_flag_id=flag_id
        ).first() is None


# 11. Navigation and direct route behavior use the same effective flag state.
def test_navigation_and_route_use_same_effective_flag_state(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        flag_id = FeatureFlag.query.filter_by(key="learning_center").one().id

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    client.post(f"/models/flags/{flag_id}/toggle", data={}, follow_redirects=True)  # disable for Customer B

    # Nav must hide the link...
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert "/agents/learning-center" not in body

    # ...and the route itself must reject direct access, not just hide the link.
    resp = client.get("/agents/learning-center")
    assert resp.status_code in (302, 303)
    resp2 = client.get("/agents/learning-center", follow_redirects=True)
    assert "not currently enabled" in resp2.get_data(as_text=True).lower()


# 12. Global roles, navigation layout, release notes, and doc prompts remain global.
def test_global_entities_remain_global(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        role_count_before = Role.query.count()
        from app.models import DocPrompt, NavSection
        nav_section_count_before = NavSection.query.count()
        doc_prompt_count_before = DocPrompt.query.count()

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)

    with full_app.app_context():
        # Creating a brand-new tenant must not create per-tenant copies of any
        # of these — they stay single, global rows.
        assert Role.query.count() == role_count_before
        assert NavSection.query.count() == nav_section_count_before
        assert DocPrompt.query.count() == doc_prompt_count_before

    resp = client.get("/models/")
    body = resp.get_data(as_text=True)
    assert "Sections (Global)" in body
    assert "Help Prompts (Global)" in body
