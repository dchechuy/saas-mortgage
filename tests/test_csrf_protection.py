"""Repository-wide CSRF protection regression tests.

These tests deliberately enable Flask-WTF; the rest of the pre-existing
suite disables it so legacy route tests can continue focusing on their own
authorization and tenancy concerns.
"""
import io
import re

import pytest

from app.extensions import db
from app.models import AgentConversation, AiAgent, FeatureFlag, Tenant, TenantFeatureFlag, User

from .conftest import create_tenant, create_user, set_password


_TOKEN_RE = re.compile(rb'<meta name="csrf-token" content="([^"]+)">')


@pytest.fixture()
def csrf_client(full_app):
    previous = full_app.config.get("WTF_CSRF_ENABLED")
    full_app.config["WTF_CSRF_ENABLED"] = True
    try:
        yield full_app.test_client()
    finally:
        full_app.config["WTF_CSRF_ENABLED"] = previous


def _token(response) -> str:
    match = _TOKEN_RE.search(response.data)
    assert match, "Rendered page did not expose the shared CSRF meta token"
    return match.group(1).decode()


def _login(full_app, client, username="admin", password="Test-1234") -> str:
    set_password(full_app, username, password)
    login_page = client.get("/login")
    token = _token(login_page)
    response = client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return _token(response)


def test_login_requires_csrf_without_redirect_loop(full_app, csrf_client):
    set_password(full_app, "admin", "Test-1234")

    response = csrf_client.post(
        "/login",
        data={"username": "admin", "password": "Test-1234"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    follow = csrf_client.get(response.headers["Location"])
    assert follow.status_code == 200
    assert b"form expired or could not be verified" in follow.data


def test_tenant_switch_rejects_missing_and_invalid_token_and_reuses_valid_token(full_app, csrf_client):
    token = _login(full_app, csrf_client)

    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        admin_id = admin.id
        original_target = admin.last_active_tenant_id

    missing = csrf_client.post(
        "/tenants/switch", data={"tenant_id": cofficiency.id, "next": "/"}, follow_redirects=False
    )
    invalid = csrf_client.post(
        "/tenants/switch",
        data={"tenant_id": cofficiency.id, "next": "/", "csrf_token": "invalid"},
        follow_redirects=False,
    )
    assert missing.status_code == invalid.status_code == 302

    with full_app.app_context():
        assert db.session.get(User, admin_id).last_active_tenant_id == original_target

    first = csrf_client.post(
        "/tenants/switch",
        data={"tenant_id": cofficiency.id, "next": "/", "csrf_token": token},
        follow_redirects=False,
    )
    second = csrf_client.post(
        "/tenants/switch",
        data={"tenant_id": advantagefirst.id, "next": "/", "csrf_token": token},
        follow_redirects=False,
    )
    assert first.status_code == second.status_code == 302
    with full_app.app_context():
        assert db.session.get(User, admin_id).last_active_tenant_id == advantagefirst.id


def test_cross_site_forms_cannot_create_user_archive_tenant_or_change_flag(full_app, csrf_client):
    _login(full_app, csrf_client)
    target_tenant_id = create_tenant(full_app, "CSRF Target", "csrf-target")

    with full_app.app_context():
        target = db.session.get(Tenant, target_tenant_id)
        flag = FeatureFlag.query.filter_by(key="conversations").one()
        initial_override_count = TenantFeatureFlag.query.filter_by(feature_flag_id=flag.id).count()

    assert csrf_client.post(
        "/users/add",
        data={"username": "csrf-created", "email": "csrf@example.com", "password": "Password-123"},
    ).status_code == 302
    assert csrf_client.post(f"/tenants/{target_tenant_id}/archive").status_code == 302
    assert csrf_client.post(f"/models/flags/{flag.id}/toggle", data={"is_enabled": "1"}).status_code == 302

    with full_app.app_context():
        assert User.query.filter_by(username="csrf-created").first() is None
        assert db.session.get(Tenant, target_tenant_id).is_active is True
        assert TenantFeatureFlag.query.filter_by(feature_flag_id=flag.id).count() == initial_override_count


def test_ajax_header_allows_conversation_mutation_but_not_cross_tenant_access(full_app, csrf_client):
    token = _login(full_app, csrf_client)

    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        agent = AiAgent.query.filter_by(tenant_id=advantagefirst.id).first()
        assert agent is not None
        conversation = AgentConversation(
            tenant_id=advantagefirst.id,
            title="CSRF test",
            ai_agent_id=agent.id,
            user_id=admin.id,
        )
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()

    ok = csrf_client.post(
        f"/agents/{conversation_id}/favorite",
        headers={"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest"},
    )
    assert ok.status_code == 200
    assert ok.get_json()["ok"] is True

    csrf_client.post(
        "/tenants/switch",
        data={"tenant_id": cofficiency.id, "next": "/", "csrf_token": token},
    )
    denied = csrf_client.post(
        f"/agents/{conversation_id}/favorite",
        headers={"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest"},
    )
    assert denied.status_code == 404


def test_ajax_header_allows_quality_mutation(full_app, csrf_client, fake_skunkbox):
    tenant_id = create_tenant(full_app, "CSRF Quality", "csrf-quality")
    create_user(full_app, "csrf_quality_admin", tenant_id, role="admin")
    with full_app.app_context():
        flag = FeatureFlag.query.filter_by(key="ai_quality").one()
        db.session.add(TenantFeatureFlag(
            tenant_id=tenant_id, feature_flag_id=flag.id, is_enabled=True
        ))
        db.session.commit()

    token = _login(full_app, csrf_client, "csrf_quality_admin")
    response = csrf_client.post(
        "/quality/components/add",
        data={"title": "CSRF-Protected Component"},
        headers={"X-CSRFToken": token, "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert any(c["title"] == "CSRF-Protected Component" for c in fake_skunkbox.components.values())


def test_file_upload_form_renders_hidden_csrf_token(full_app, csrf_client):
    _login(full_app, csrf_client)
    with full_app.app_context():
        user_id = User.query.filter_by(username="jane").one().id
    response = csrf_client.get(f"/users/{user_id}/edit")

    assert response.status_code == 200
    assert response.data.count(b'name="csrf_token"') >= 2
    assert b'enctype="multipart/form-data"' in response.data


def test_logout_password_change_and_file_upload_remain_functional(
    full_app, csrf_client, tmp_path
):
    token = _login(full_app, csrf_client)
    full_app.config["AVATAR_UPLOAD_FOLDER"] = str(tmp_path)

    password = csrf_client.post(
        "/users/change-password",
        data={
            "current_password": "Test-1234",
            "new_password": "New-Test-1234",
            "confirm_password": "New-Test-1234",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert password.status_code == 302

    upload = csrf_client.post(
        "/users/me/upload-avatar",
        data={
            "avatar": (io.BytesIO(b"test image bytes"), "avatar.png"),
            "csrf_token": token,
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload.status_code == 302
    with full_app.app_context():
        admin = User.query.filter_by(username="admin").one()
        assert admin.check_password("New-Test-1234")
        assert admin.avatar == f"user_{admin.id}.png"
        assert (tmp_path / admin.avatar).read_bytes() == b"test image bytes"

    logout = csrf_client.post(
        "/logout", data={"csrf_token": token}, follow_redirects=False
    )
    assert logout.status_code == 302
    assert logout.headers["Location"].endswith("/login")
    assert csrf_client.get("/users/").status_code == 302
