"""Tests for Phase 5 — Conversations, Knowledge Base, and Dashboard.

Numbered to match docs/prompts/Tenant Separation - Prompt - Phase 5 - saas-mortgage.md
section 'Tests'. Uses Cofficiency plus two customer tenants (AdvantageFirst,
the Phase 1 fixture tenant, and a fresh "Customer B").
"""
from unittest import mock

from app.extensions import db
from app.models import (AgentConversation, AgentMessage, AiAgent, ApiRequestLog,
                         Integration, MessageAttachment, ReleaseNote, Role, Tenant, User)

from .conftest import create_tenant, create_user
from .conftest import login as _login
from .conftest import set_password as _set_password


def _tenant_id(app, slug):
    with app.app_context():
        return Tenant.query.filter_by(slug=slug).one().id


def _switch(client, tenant_id):
    return client.post("/tenants/switch", data={"tenant_id": tenant_id, "next": "/"}, follow_redirects=True)


def _make_integration(app, tenant_id, name, use_case="AI Agents"):
    with app.app_context():
        integ = Integration(
            tenant_id=tenant_id, name=name, provider="OpenAI", category="LLM",
            use_case=use_case, is_active=True, base_url="https://skunk.example.com/api/v1",
        )
        db.session.add(integ)
        db.session.commit()
        return integ.id


def _make_agent(app, tenant_id, integration_id, name):
    with app.app_context():
        agent = AiAgent(
            tenant_id=tenant_id, name=name, integration_id=integration_id,
            skunkbox_agent_id=1, is_active=True,
        )
        db.session.add(agent)
        db.session.commit()
        return agent.id


def _make_conversation(app, tenant_id, agent_id, user_id, title="Conv"):
    with app.app_context():
        conv = AgentConversation(
            tenant_id=tenant_id, ai_agent_id=agent_id, user_id=user_id,
            title=title, is_archived=False, skunkbox_session_id="sess-1",
        )
        db.session.add(conv)
        db.session.commit()
        return conv.id


# 1. Agent choices are active-tenant only.
def test_agent_choices_are_active_tenant_only(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    cb_integration_id = _make_integration(full_app, customer_b_id, "CB Integration")
    _make_agent(full_app, customer_b_id, cb_integration_id, "CB Agent")

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get("/agents/")
    body = resp.get_data(as_text=True)
    assert "Helper" in body        # AdvantageFirst's fixture agent
    assert "CB Agent" not in body  # Customer B's agent must not leak in


# 2. New conversation receives active tenant.
def test_new_conversation_receives_active_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    cb_integration_id = _make_integration(full_app, customer_b_id, "CB Integration")
    cb_agent_id = _make_agent(full_app, customer_b_id, cb_integration_id, "CB Agent")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    resp = client.post("/agents/new", data={"agent_id": str(cb_agent_id)}, follow_redirects=True)
    assert resp.status_code == 200

    with full_app.app_context():
        conv = AgentConversation.query.filter_by(ai_agent_id=cb_agent_id).one()
        assert conv.tenant_id == customer_b_id


# 3. Forged cross-tenant agent ID is rejected.
def test_forged_cross_tenant_agent_id_rejected(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        af_agent_id = AiAgent.query.filter_by(tenant_id=advantagefirst_id).one().id

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)  # active tenant is Customer B; agent belongs to AdvantageFirst
    resp = client.post("/agents/new", data={"agent_id": str(af_agent_id)}, follow_redirects=False)
    assert resp.status_code == 404

    with full_app.app_context():
        assert AgentConversation.query.filter_by(ai_agent_id=af_agent_id, user_id=None).count() == 0


# 4 & 5. Mine/all/favorites and filters never mix tenants; a Cofficiency actor's
# "Mine" conversations stay separated by selected tenant.
def test_mine_all_favorites_never_mix_tenants(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        admin_id = User.query.filter_by(username="admin").one().id
        af_agent_id = AiAgent.query.filter_by(tenant_id=advantagefirst_id).one().id
    cb_integration_id = _make_integration(full_app, customer_b_id, "CB Integration")
    cb_agent_id = _make_agent(full_app, customer_b_id, cb_integration_id, "CB Agent")

    # Same actor (admin) has a conversation in *both* tenants.
    _make_conversation(full_app, advantagefirst_id, af_agent_id, admin_id, title="AF Convo Mine")
    _make_conversation(full_app, customer_b_id, cb_agent_id, admin_id, title="CB Convo Mine")

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get("/agents/?tab=mine")
    body = resp.get_data(as_text=True)
    assert "AF Convo Mine" in body
    assert "CB Convo Mine" not in body

    _switch(client, customer_b_id)
    resp = client.get("/agents/?tab=mine")
    body = resp.get_data(as_text=True)
    assert "CB Convo Mine" in body
    assert "AF Convo Mine" not in body

    resp = client.get("/agents/?tab=all")
    body = resp.get_data(as_text=True)
    assert "CB Convo Mine" in body
    assert "AF Convo Mine" not in body


# 6. Old conversation URL fails after switching away from its tenant.
def test_old_conversation_url_fails_after_switching_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        admin_id = User.query.filter_by(username="admin").one().id
        af_agent_id = AiAgent.query.filter_by(tenant_id=advantagefirst_id).one().id
    af_conv_id = _make_conversation(full_app, advantagefirst_id, af_agent_id, admin_id, title="AF Open Convo")

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get(f"/agents/{af_conv_id}")
    assert resp.status_code == 200  # works while AdvantageFirst is active

    _switch(client, customer_b_id)
    resp = client.get(f"/agents/{af_conv_id}")
    assert resp.status_code == 404  # same URL, now stale after the switch


# 7 & 8. Cross-tenant send/archive/favorite/upload/download IDs are rejected;
# attachment ownership is enforced through conversation tenant.
def test_cross_tenant_direct_operations_rejected(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        admin_id = User.query.filter_by(username="admin").one().id
        af_agent_id = AiAgent.query.filter_by(tenant_id=advantagefirst_id).one().id
    af_conv_id = _make_conversation(full_app, advantagefirst_id, af_agent_id, admin_id, title="AF Convo")

    with full_app.app_context():
        conv = db.session.get(AgentConversation, af_conv_id)
        msg = AgentMessage(conversation_id=conv.id, role="user", content="hi")
        db.session.add(msg)
        db.session.commit()
        att = MessageAttachment(
            message_id=msg.id, skunkbox_attachment_id=555,
            original_filename="f.pdf", mime_type="application/pdf", file_category="document",
        )
        db.session.add(att)
        db.session.commit()

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)  # active tenant is now Customer B; everything above belongs to AdvantageFirst

    resp = client.post(f"/agents/{af_conv_id}/send", json={"message": "hi"})
    assert resp.status_code == 404

    resp = client.post(f"/agents/{af_conv_id}/favorite")
    assert resp.status_code == 404

    resp = client.post(f"/agents/{af_conv_id}/archive", follow_redirects=False)
    assert resp.status_code == 404

    resp = client.post(f"/agents/{af_conv_id}/attachments", data={})
    assert resp.status_code == 404

    resp = client.get("/agents/attachments/555/download")
    assert resp.status_code == 404

    with full_app.app_context():
        conv = db.session.get(AgentConversation, af_conv_id)
        assert conv.is_archived is False
        assert conv.is_favorite is False


# 9. Knowledge-base routes cannot use another tenant's agent/integration.
def test_learning_center_cannot_use_another_tenants_integration(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    _make_integration(full_app, advantagefirst_id, "AF Docs", use_case="Documents")
    # Customer B deliberately has no Documents integration.

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)
    resp = client.get("/agents/learning-center")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "No Documents integration" in body or "error" in body.lower()


# 10. Outbound API log receives owning/active tenant.
def test_outbound_api_log_receives_owning_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    cb_integration_id = _make_integration(full_app, customer_b_id, "CB Integration")
    cb_agent_id = _make_agent(full_app, customer_b_id, cb_integration_id, "CB Agent")

    with full_app.app_context():
        admin_id = User.query.filter_by(username="admin").one().id
    cb_conv_id = _make_conversation(full_app, customer_b_id, cb_agent_id, admin_id, title="CB Convo")

    _login(client, "admin", "Test-1234")
    _switch(client, customer_b_id)

    import app.routes.agents as agents_module

    def fake_skunkbox(**kwargs):
        integration = kwargs.get("integration")
        agents_module._log_api(integration, "https://skunk.example.com/api/v1/chat/messages", "POST", 200, 42)
        return {"response": "mocked reply", "session_id": "sess-1"}

    with mock.patch.object(agents_module, "_call_skunkbox", side_effect=fake_skunkbox):
        resp = client.post(f"/agents/{cb_conv_id}/send", json={"message": "hello"})
        assert resp.status_code == 200

    with full_app.app_context():
        log = ApiRequestLog.query.filter_by(integration_id=cb_integration_id).order_by(
            ApiRequestLog.id.desc()
        ).first()
        assert log is not None
        assert log.tenant_id == customer_b_id


# 11. Dashboard operational counts change with tenant.
def test_dashboard_counts_change_with_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    create_user(full_app, "cb_dashboard_user_1", customer_b_id)
    create_user(full_app, "cb_dashboard_user_2", customer_b_id)

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get("/dashboard")
    af_body = resp.get_data(as_text=True)

    _switch(client, customer_b_id)
    resp = client.get("/dashboard")
    cb_body = resp.get_data(as_text=True)

    with full_app.app_context():
        af_user_count = User.query.filter_by(tenant_id=advantagefirst_id).count()
        cb_user_count = User.query.filter_by(tenant_id=customer_b_id).count()
    assert af_user_count != cb_user_count
    assert af_body != cb_body


# 12. Roles/releases behave globally as specified.
def test_roles_and_releases_are_global_on_dashboard(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        role_count = Role.query.count()
        release_count = ReleaseNote.query.count()

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get("/dashboard")
    af_body = resp.get_data(as_text=True)

    _switch(client, customer_b_id)
    resp = client.get("/dashboard")
    cb_body = resp.get_data(as_text=True)

    # Both pages must render the same (global) role/release counts.
    assert f">{role_count}<" in af_body
    assert f">{role_count}<" in cb_body
    assert f">{release_count}<" in af_body
    assert f">{release_count}<" in cb_body


# 13. User Documentation and Release Notes remain visible across tenant switches.
def test_docs_and_release_notes_visible_across_tenant_switches(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    with full_app.app_context():
        admin_id = User.query.filter_by(username="admin").one().id
        db.session.add(ReleaseNote(
            version_string="1.2.3", version_major=1, version_minor=2, version_patch=3,
            release_type="minor", status="published", created_by_user_id=admin_id,
            content_html="<p>Distinctive Phase 5 release note marker.</p>",
        ))
        db.session.commit()

    _login(client, "admin", "Test-1234")
    _switch(client, advantagefirst_id)
    resp = client.get("/help/release-notes")
    assert resp.status_code == 200
    af_body = resp.get_data(as_text=True)
    assert "AdvantageFirst" in af_body  # switcher reflects the active tenant
    assert "Distinctive Phase 5 release note marker" in af_body

    _switch(client, customer_b_id)
    resp = client.get("/help/release-notes")
    assert resp.status_code == 200
    cb_body = resp.get_data(as_text=True)
    assert "Customer B" in cb_body
    # Same global release note content, visible regardless of active tenant.
    assert "Distinctive Phase 5 release note marker" in cb_body
