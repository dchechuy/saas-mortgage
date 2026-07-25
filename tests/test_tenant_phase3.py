"""Tests for Phase 3 — Tenant-Isolated User Management.

Numbered to match docs/prompts/Tenant Separation - Prompt - Phase 3 - saas-mortgage.md
section 'Tests'. Uses three tenants: Cofficiency (protected/internal),
AdvantageFirst (the Phase 1 fixture's historical external tenant), and a third
customer tenant ("Customer B") created fresh in these tests.
"""
from app.extensions import db
from app.models import Tenant, User, UserActivityLog

from .conftest import create_tenant, create_user
from .conftest import ensure_baseline_permissions as _ensure_baseline_permissions
from .conftest import login as _login
from .conftest import set_password as _set_password


def _tenant_id(app, slug):
    with app.app_context():
        return Tenant.query.filter_by(slug=slug).one().id


# 1 & 2. User lists and counts are tenant-isolated; Cofficiency lists only Cofficiency users.
def test_user_list_and_counts_are_tenant_isolated(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    cofficiency_id = _tenant_id(full_app, "cofficiency")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")
    create_user(full_app, "coffi_two", cofficiency_id)

    _login(client, "admin", "Test-1234")

    # admin's remembered active tenant is AdvantageFirst (Phase 1 migration semantics).
    resp = client.get("/users/")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "jane" in body  # AdvantageFirst user
    assert "coffi_two" not in body  # Cofficiency user must not leak in

    # Switch to Cofficiency — now only Cofficiency users should show.
    client.post("/tenants/switch", data={"tenant_id": cofficiency_id, "next": "/users/"}, follow_redirects=True)
    resp = client.get("/users/")
    body = resp.get_data(as_text=True)
    assert "coffi_two" in body
    assert "jane" not in body


# 3. Cofficiency user switching to customer A (a third tenant) sees customer A users.
def test_cofficiency_user_switching_sees_correct_tenant_users(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")
    create_user(full_app, "cb_user", customer_b_id)

    _login(client, "admin", "Test-1234")
    client.post("/tenants/switch", data={"tenant_id": customer_b_id, "next": "/users/"}, follow_redirects=True)

    resp = client.get("/users/")
    body = resp.get_data(as_text=True)
    assert "<strong>cb_user</strong>" in body
    assert "<strong>jane</strong>" not in body  # AdvantageFirst user must not leak in
    # Cofficiency's own admin must not leak in either — checked against the table
    # cell markup, not a bare substring, since "admin" also appears in the logged-in
    # user's own header profile chip (@admin) regardless of which tenant is active.
    assert "<strong>admin</strong>" not in body


# 4. External user sees only home-tenant users.
def test_external_user_sees_only_home_tenant_users(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "jane", "Test-1234")
    cofficiency_id = _tenant_id(full_app, "cofficiency")
    create_user(full_app, "coffi_only", cofficiency_id)

    _login(client, "jane", "Test-1234")
    resp = client.get("/users/")
    body = resp.get_data(as_text=True)
    assert "jane" in body
    assert "coffi_only" not in body
    assert "admin" not in body


# 5 & 6. Added user receives active tenant automatically; forged tenant_id cannot alter assignment.
def test_add_user_gets_active_tenant_and_ignores_forged_tenant_id(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    client.post("/tenants/switch", data={"tenant_id": customer_b_id, "next": "/"}, follow_redirects=True)

    resp = client.post(
        "/users/add",
        data={
            "username": "new_cb_user", "email": "new_cb_user@example.com",
            "password": "Somepass123", "role": "member",
            "tenant_id": "999999",  # forged — must be ignored entirely
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with full_app.app_context():
        new_user = User.query.filter_by(username="new_cb_user").one()
        assert new_user.tenant_id == customer_b_id
        assert new_user.tenant_id != 999999


# 7. Existing user's tenant cannot be changed (even via a forged edit POST).
def test_existing_user_tenant_cannot_be_changed_via_edit(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")

    with full_app.app_context():
        jane_id = User.query.filter_by(username="jane").one().id

    _login(client, "admin", "Test-1234")
    client.post("/tenants/switch", data={"tenant_id": advantagefirst_id, "next": "/"}, follow_redirects=True)

    resp = client.post(
        f"/users/{jane_id}/edit",
        data={
            "username": "jane", "email": "jane@example.com", "role": "member",
            "tenant_id": "999999",  # forged — the route doesn't even read this field
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with full_app.app_context():
        jane = db.session.get(User, jane_id)
        assert jane.tenant_id == advantagefirst_id


# 8. Cross-tenant edit/toggle/avatar IDs are rejected (404).
def test_cross_tenant_edit_toggle_avatar_rejected(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    cofficiency_id = _tenant_id(full_app, "cofficiency")
    advantagefirst_id = _tenant_id(full_app, "advantagefirst")

    with full_app.app_context():
        jane_id = User.query.filter_by(username="jane").one().id

    _login(client, "admin", "Test-1234")
    # admin's active tenant defaults to Cofficiency here (fresh login, no switch yet
    # in this test) only if last_active_tenant_id was reset; Phase 1 seeds it to
    # AdvantageFirst, so switch explicitly to Cofficiency to exercise the cross-tenant path.
    client.post("/tenants/switch", data={"tenant_id": cofficiency_id, "next": "/"}, follow_redirects=True)

    # jane belongs to AdvantageFirst; active tenant is now Cofficiency -> cross-tenant.
    resp = client.get(f"/users/{jane_id}/edit")
    assert resp.status_code == 404

    resp = client.post(f"/users/{jane_id}/toggle")
    assert resp.status_code == 404

    resp = client.post(f"/users/{jane_id}/upload-avatar", data={})
    assert resp.status_code == 404

    with full_app.app_context():
        jane = db.session.get(User, jane_id)
        assert jane.is_active is True  # toggle must not have applied


# 9. Global username/email uniqueness still applies (across tenants).
def test_username_and_email_remain_globally_unique_across_tenants(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    client.post("/tenants/switch", data={"tenant_id": customer_b_id, "next": "/"}, follow_redirects=True)

    # 'jane' already exists in AdvantageFirst — must be rejected even though we're
    # now creating in a completely different (Customer B) tenant.
    resp = client.post(
        "/users/add",
        data={"username": "jane", "email": "jane2@example.com", "password": "Somepass123", "role": "member"},
        follow_redirects=True,
    )
    body = resp.get_data(as_text=True)
    assert "already taken" in body.lower()

    resp = client.post(
        "/users/add",
        data={"username": "jane_new", "email": "jane@example.com", "password": "Somepass123", "role": "member"},
        follow_redirects=True,
    )
    body = resp.get_data(as_text=True)
    assert "already registered" in body.lower()

    with full_app.app_context():
        assert User.query.filter_by(username="jane_new").first() is None


# 10. Global roles remain selectable according to existing permissions.
def test_global_roles_remain_selectable(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    _login(client, "admin", "Test-1234")

    resp = client.get("/users/add")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # Roles come from the global Role table, not anything tenant-scoped.
    assert "member" in body


# 11. Activity rows use active tenant while actor remains Cofficiency.
def test_activity_uses_active_tenant_while_actor_stays_cofficiency(full_app, client):
    _ensure_baseline_permissions(full_app)
    _set_password(full_app, "admin", "Test-1234")
    cofficiency_id = _tenant_id(full_app, "cofficiency")
    customer_b_id = create_tenant(full_app, "Customer B", "customer-b")

    _login(client, "admin", "Test-1234")
    client.post("/tenants/switch", data={"tenant_id": customer_b_id, "next": "/"}, follow_redirects=True)

    client.post(
        "/users/add",
        data={
            "username": "cb_new_user", "email": "cb_new_user@example.com",
            "password": "Somepass123", "role": "member",
        },
        follow_redirects=True,
    )

    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        created_log = UserActivityLog.query.filter_by(action="user.created").order_by(
            UserActivityLog.id.desc()
        ).first()
        assert created_log is not None
        assert created_log.user_id == admin.id  # actor is still the Cofficiency admin
        assert created_log.tenant_id == customer_b_id  # but event belongs to Customer B
        assert admin.tenant_id == cofficiency_id  # actor's home tenant never changed
