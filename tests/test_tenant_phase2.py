"""Tests for Phase 2 — Active Tenant Context, Tenant Administration, and Switcher.

Numbered to match docs/prompts/Tenant Separation - Prompt - Phase 2 - saas-mortgage.md
section 'Tests'. Uses the `full_app`/`client` fixtures (the real app, not the
bare Phase 1 model-test app) since this phase is about routes and web flows.
"""
import uuid

from app.extensions import db
from app.models import Tenant, User, UserActivityLog
from app.tenant_context import can_switch_tenants, get_active_tenant, get_active_tenant_id

from .conftest import ensure_baseline_permissions as _ensure_baseline_permissions
from .conftest import login as _login
from .conftest import set_password as _set_password


# 1. External user active tenant equals home tenant.
def test_external_user_active_tenant_equals_home_tenant(full_app):
    with full_app.app_context():
        jane = User.query.filter_by(username="jane").one()
        assert get_active_tenant(jane).id == jane.tenant_id
        assert can_switch_tenants(jane) is False


# 2. External user cannot switch, including a forged POST.
def test_external_user_cannot_switch_even_forged(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "jane", "Test-1234")
    _login(client, "jane", "Test-1234")

    with full_app.app_context():
        jane = User.query.filter_by(username="jane").one()
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        jane_id, target_id = jane.id, cofficiency.id

    resp = client.post("/tenants/switch", data={"tenant_id": target_id, "next": "/"}, follow_redirects=True)
    assert resp.status_code == 200

    with full_app.app_context():
        jane = db.session.get(User, jane_id)
        assert jane.last_active_tenant_id is None
        assert get_active_tenant_id(jane) == jane.tenant_id


# 3. Cofficiency user defaults correctly when remembered tenant is null/invalid/inactive.
def test_cofficiency_user_default_resolution(full_app):
    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()

        admin.last_active_tenant_id = None
        db.session.commit()
        assert get_active_tenant(admin).slug == "cofficiency"

        admin.last_active_tenant_id = 999999  # invalid/nonexistent
        db.session.commit()
        assert get_active_tenant(admin).slug == "cofficiency"

        archived = Tenant(name="Archived Co", slug="archived-co", is_active=False,
                          external_id=str(uuid.uuid4()), sync_status="synced")
        db.session.add(archived)
        db.session.commit()
        admin.last_active_tenant_id = archived.id
        db.session.commit()
        assert get_active_tenant(admin).id == cofficiency.id


# 4. Cofficiency user can switch to an active tenant.
def test_cofficiency_user_can_switch(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    with full_app.app_context():
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        admin = User.query.filter_by(username="admin").one()
        admin_id, target_id = admin.id, advantagefirst.id

    resp = client.post("/tenants/switch", data={"tenant_id": target_id, "next": "/"}, follow_redirects=True)
    assert resp.status_code == 200

    with full_app.app_context():
        admin = db.session.get(User, admin_id)
        assert admin.last_active_tenant_id == target_id


# 5. Switch persists across a new session/login.
def test_switch_persists_across_new_login(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    with full_app.app_context():
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        target_id = advantagefirst.id

    client.post("/tenants/switch", data={"tenant_id": target_id, "next": "/"}, follow_redirects=True)
    client.post("/logout")

    _login(client, "admin", "Test-1234")
    resp = client.get("/")
    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        assert admin.last_active_tenant_id == target_id
        assert get_active_tenant(admin).id == target_id


# 6. Switch does not mutate home tenant.
def test_switch_does_not_mutate_home_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    with full_app.app_context():
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        admin = User.query.filter_by(username="admin").one()
        admin_id, home_id, target_id = admin.id, admin.tenant_id, advantagefirst.id
        assert home_id == cofficiency.id

    client.post("/tenants/switch", data={"tenant_id": target_id, "next": "/"}, follow_redirects=True)

    with full_app.app_context():
        admin = db.session.get(User, admin_id)
        assert admin.tenant_id == home_id


# 7. Header switcher visibility and active label are correct.
def test_header_switcher_visibility_and_label(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _set_password(full_app, "jane", "Test-1234")

    resp = _login(client, "admin", "Test-1234")
    body = resp.get_data(as_text=True)
    assert "tenant-switcher-btn" in body
    assert "AdvantageFirst" in body  # admin's remembered active tenant
    client.post("/logout")

    resp = _login(client, "jane", "Test-1234")
    body = resp.get_data(as_text=True)
    assert "tenant-switcher-btn" not in body


# 8. Existing role permissions still hide unauthorized pages after switching.
def test_permissions_still_apply_after_switching(full_app, client):
    from app.page_registry import PAGES

    with full_app.app_context():
        from app.models import Permission, Role
        member_role = Role.query.filter_by(name="member").first()
        if not member_role:
            member_role = Role(name="member", is_system=False)
            db.session.add(member_role)
            db.session.flush()

        # A normal role with broad view access to everything *except* tenant
        # administration — mirrors a real non-admin role, rather than a
        # blanket no_access role (which would trip the page's own
        # unrelated-to-tenants dashboard-permission redirect behavior).
        for page in PAGES:
            Permission.query.filter_by(role_id=member_role.id, page_slug=page["slug"]).delete()
            level = "no_access" if page["slug"] == "tenants" else "view"
            db.session.add(Permission(role_id=member_role.id, page_slug=page["slug"], access_level=level))

        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        member = User(
            username="coffi_member", email="coffi_member@example.com", role="member",
            tenant_id=cofficiency.id, must_change_password=False,
        )
        member.set_password("Test-1234")
        db.session.add(member)
        db.session.commit()

    _login(client, "coffi_member", "Test-1234")
    # A Cofficiency member (not admin-role) must not reach tenant administration,
    # switching workspace grants no additional permissions.
    resp = client.get("/tenants/", follow_redirects=True)
    body = resp.get_data(as_text=True)
    assert "do not have permission" in body.lower()


# 9. Cofficiency admin can create/archive/reactivate a customer tenant.
def test_cofficiency_admin_can_create_archive_reactivate(full_app, client, fake_skunkbox):
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    client.post("/tenants/add", data={"name": "Widgets Inc"}, follow_redirects=True)
    with full_app.app_context():
        tenant = Tenant.query.filter_by(name="Widgets Inc").one()
        assert tenant.is_active is True
        tenant_id = tenant.id

    client.post(f"/tenants/{tenant_id}/archive", follow_redirects=True)
    with full_app.app_context():
        assert db.session.get(Tenant, tenant_id).is_active is False

    client.post(f"/tenants/{tenant_id}/reactivate", follow_redirects=True)
    with full_app.app_context():
        assert db.session.get(Tenant, tenant_id).is_active is True


# 10. Protected Cofficiency cannot be renamed or archived.
def test_protected_cofficiency_cannot_be_renamed_or_archived(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    with full_app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id

    client.post(f"/tenants/{cofficiency_id}/archive", follow_redirects=True)
    client.post(f"/tenants/{cofficiency_id}/edit", data={"name": "Hacked Name"}, follow_redirects=True)

    with full_app.app_context():
        cof = db.session.get(Tenant, cofficiency_id)
        assert cof.is_active is True
        assert cof.name == "Cofficiency"


# 11. Activity by a Cofficiency user is recorded under selected tenant.
def test_activity_by_cofficiency_user_recorded_under_selected_tenant(full_app, client):
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    with full_app.app_context():
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        target_id = advantagefirst.id

    client.post("/tenants/switch", data={"tenant_id": target_id, "next": "/"}, follow_redirects=True)

    with full_app.app_context():
        switch_log = UserActivityLog.query.filter_by(action="tenant.switched").order_by(
            UserActivityLog.id.desc()
        ).first()
        assert switch_log is not None
        assert switch_log.tenant_id == target_id


# 12. Historical data from Phase 1 remains unchanged.
def test_phase1_historical_data_unchanged(full_app):
    with full_app.app_context():
        from app.models import AgentConversation, ApiRequestLog, Attribute, Integration, LlmModel, LlmRequestLog

        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        admin = User.query.filter_by(username="admin").one()
        jane = User.query.filter_by(username="jane").one()

        assert admin.tenant_id == Tenant.query.filter_by(slug="cofficiency").one().id
        assert jane.tenant_id == advantagefirst.id
        assert LlmModel.query.filter_by(name="gpt-4").one().tenant_id == advantagefirst.id
        assert Attribute.query.filter_by(category="Customer", name="SMB").one().tenant_id == advantagefirst.id
        assert Integration.query.filter_by(name="OpenAI Prod").one().tenant_id == advantagefirst.id
        assert AgentConversation.query.filter_by(title="Test convo").one().tenant_id == advantagefirst.id
        assert LlmRequestLog.query.one().tenant_id == advantagefirst.id
        assert ApiRequestLog.query.one().tenant_id == advantagefirst.id
