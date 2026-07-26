"""Phase 5 — Cross-System Tenant AI Assets: Cophy authoritative tenant sync.

Covers docs/prompts/Cross-System Tenant AI Assets - Prompt - Phase 5 -
saas-mortgage.md's Tests list: UUID mapping migration, local ownership
unchanged, create/edit/archive/reactivate authoritative-first behavior,
idempotent retry after partial failure, full reconciliation, duplicate/drift
detection, no local deletion/reassignment, archived active-tenant fallback,
external users cannot administer/sync tenants, active UUID derives
server-side, service secrets never reach HTML/logs.

Route-level tests use the `fake_skunkbox` fixture (tests/conftest.py) so no
real HTTP call is made. Client-level tests below patch `requests.request`
directly to exercise app/skunkbox_client.py's own retry/header/error logic.
"""
import uuid

import pytest

from app.extensions import db
from app.models import Tenant, User

from .conftest import create_tenant, create_user
from .conftest import ensure_baseline_permissions as _ensure_baseline_permissions
from .conftest import login as _login
from .conftest import set_password as _set_password


# ── UUID mapping migration / local ownership unchanged ──────────────────────

def test_seeded_tenants_have_external_id_and_synced_status(app):
    with app.app_context():
        cofficiency = Tenant.query.filter_by(slug="cofficiency").one()
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        assert cofficiency.external_id
        assert advantagefirst.external_id
        assert cofficiency.external_id != advantagefirst.external_id
        assert cofficiency.sync_status == "synced"
        assert advantagefirst.sync_status == "synced"


def test_migration_did_not_change_local_ids_or_ownership(app):
    """The Phase 1 migration attributed all pre-existing historical data to
    AdvantageFirst; Phase 5's external_id backfill must not have touched
    that — same tenant ids, same user tenant_id FKs."""
    with app.app_context():
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        jane = User.query.filter_by(username="jane").one()
        assert jane.tenant_id == advantagefirst.id


# ── skunkbox_client: idempotency, retry, secret handling ────────────────────

class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def test_create_tenant_reuses_same_idempotency_key_across_internal_retry(full_app, monkeypatch):
    """A single create_tenant() call may retry once internally (network
    error/5xx) — both attempts must carry the SAME idempotency key, never a
    freshly generated one, or skunkBOX could create two tenants."""
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = "s3cr3t-token"
    seen_keys = []

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        seen_keys.append(headers.get("Idempotency-Key"))
        if len(seen_keys) == 1:
            return _FakeResponse(500, {"message": "boom"})
        return _FakeResponse(201, {
            "public_id": str(uuid.uuid4()), "name": "Widgets", "slug": "widgets",
            "is_active": True, "is_protected": False,
        })

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    from app import skunkbox_client
    with full_app.app_context():
        result = skunkbox_client.create_tenant("Widgets", idempotency_key="fixed-key-123")

    assert result["name"] == "Widgets"
    assert seen_keys == ["fixed-key-123", "fixed-key-123"]


def test_request_does_not_retry_a_bare_mutation_without_idempotency_key(full_app, monkeypatch):
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = "s3cr3t-token"
    call_count = {"n": 0}

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        call_count["n"] += 1
        return _FakeResponse(500, {"message": "boom"})

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    from app.skunkbox_client import SkunkBoxClientError, update_tenant
    with full_app.app_context():
        with pytest.raises(SkunkBoxClientError):
            update_tenant(str(uuid.uuid4()), "New Name")

    assert call_count["n"] == 1


def test_missing_secret_raises_before_any_http_call(full_app, monkeypatch):
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = ""
    called = {"n": 0}

    def fake_request(*args, **kwargs):
        called["n"] += 1
        return _FakeResponse(200, {})

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    from app.skunkbox_client import SkunkBoxClientError, list_tenants
    with full_app.app_context():
        with pytest.raises(SkunkBoxClientError):
            list_tenants()

    assert called["n"] == 0


def test_secret_never_appears_in_logs_on_failure(full_app, monkeypatch, caplog):
    secret = "s3cr3t-token-should-never-be-logged"
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = secret

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        return _FakeResponse(500, {"message": "boom"})

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    from app.skunkbox_client import SkunkBoxClientError, update_tenant
    with full_app.app_context():
        with pytest.raises(SkunkBoxClientError):
            with caplog.at_level("WARNING"):
                update_tenant(str(uuid.uuid4()), "New Name")

    for record in caplog.records:
        assert secret not in record.getMessage()


def test_secret_never_rendered_in_tenant_list_html(full_app, monkeypatch):
    secret = "s3cr3t-token-should-never-render"
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = secret
    _set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin", "Test-1234")

    resp = client.get("/tenants/")
    assert secret not in resp.get_data(as_text=True)


# ── Route-level: authoritative-first create/edit/archive/reactivate ─────────

def test_add_tenant_calls_skunkbox_before_any_local_row_exists(full_app, fake_skunkbox):
    _set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin", "Test-1234")

    client.post("/tenants/add", data={"name": "Skunk First Co"}, follow_redirects=True)

    assert any(call[0] == "create_tenant" for call in fake_skunkbox.calls)
    with full_app.app_context():
        tenant = Tenant.query.filter_by(name="Skunk First Co").one()
        assert tenant.external_id in fake_skunkbox.tenants
        assert tenant.sync_status == "synced"


def test_add_tenant_creates_no_local_row_when_skunkbox_rejects(full_app, fake_skunkbox):
    """skunkBOX already knows this name (no local mirror row exists for it
    yet, so Cophy's own _name_taken() pre-check can't catch it) — the create
    must still fail cleanly with zero local rows, proving there is no
    local-only creation fallback."""
    fake_skunkbox.seed("Remote Only Co", "remote-only-co")
    _set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin", "Test-1234")

    resp = client.post("/tenants/add", data={"name": "Remote Only Co"}, follow_redirects=True)

    assert b"Could not create tenant in skunkBOX" in resp.data
    with full_app.app_context():
        assert Tenant.query.filter_by(name="Remote Only Co").first() is None


def test_edit_archive_reactivate_go_through_skunkbox_first(full_app, fake_skunkbox):
    tenant_id = create_tenant(full_app, "Roundtrip Co", "roundtrip-co")
    with full_app.app_context():
        external_id = db.session.get(Tenant, tenant_id).external_id
        fake_skunkbox.seed("Roundtrip Co", "roundtrip-co", external_id=external_id)

    _set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin", "Test-1234")

    client.post(f"/tenants/{tenant_id}/edit", data={"name": "Roundtrip Renamed"}, follow_redirects=True)
    with full_app.app_context():
        assert db.session.get(Tenant, tenant_id).name == "Roundtrip Renamed"
    assert ("update_tenant", (external_id, "Roundtrip Renamed"), {}) in fake_skunkbox.calls

    client.post(f"/tenants/{tenant_id}/archive", follow_redirects=True)
    with full_app.app_context():
        assert db.session.get(Tenant, tenant_id).is_active is False
    assert any(call[0] == "archive_tenant" for call in fake_skunkbox.calls)

    client.post(f"/tenants/{tenant_id}/reactivate", follow_redirects=True)
    with full_app.app_context():
        assert db.session.get(Tenant, tenant_id).is_active is True
    assert any(call[0] == "reactivate_tenant" for call in fake_skunkbox.calls)


# ── Idempotent retry after partial failure ───────────────────────────────────

def test_partial_local_failure_recovers_idempotently_via_reconciliation(full_app, fake_skunkbox, monkeypatch):
    """skunkBOX accepts the create, but the local upsert then fails
    unexpectedly (e.g. a transient DB error). Re-running reconciliation
    afterward must converge to exactly one local row for it — not zero
    (stuck) and not two (duplicated) — without ever calling create_tenant
    again."""
    import app.routes.tenants as tenants_route

    original_upsert = tenants_route.upsert_tenant_from_remote
    state = {"raised": False}

    def flaky_upsert(remote):
        if not state["raised"]:
            state["raised"] = True
            raise RuntimeError("simulated transient local failure")
        return original_upsert(remote)

    monkeypatch.setattr(tenants_route, "upsert_tenant_from_remote", flaky_upsert)

    _set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin", "Test-1234")

    resp = client.post("/tenants/add", data={"name": "Flaky Co"}, follow_redirects=True)
    assert b"saving it locally failed unexpectedly" in resp.data or b"Run tenant reconciliation" in resp.data

    with full_app.app_context():
        assert Tenant.query.filter_by(name="Flaky Co").first() is None

    create_calls_before = [c for c in fake_skunkbox.calls if c[0] == "create_tenant"]
    assert len(create_calls_before) == 1

    from app.services.tenant_sync import run_reconciliation
    with full_app.app_context():
        summary = run_reconciliation()
        assert summary["created"] == 1
        assert Tenant.query.filter_by(name="Flaky Co").count() == 1

    # Re-running again is idempotent: no duplicate, no further skunkBOX writes.
    with full_app.app_context():
        summary2 = run_reconciliation()
        assert summary2["updated"] == 1
        assert Tenant.query.filter_by(name="Flaky Co").count() == 1

    create_calls_after = [c for c in fake_skunkbox.calls if c[0] == "create_tenant"]
    assert len(create_calls_after) == 1


# ── Full reconciliation / duplicate detection / no deletion ────────────────

def test_reconciliation_creates_updates_and_flags_missing_without_deleting(full_app, fake_skunkbox):
    with full_app.app_context():
        stale_id = create_tenant(full_app, "Stale Co", "stale-co")
        stale_tenant = db.session.get(Tenant, stale_id)
        stale_external_id = stale_tenant.external_id
        renamed_id = create_tenant(full_app, "Old Name Co", "old-name-co")
        renamed_tenant = db.session.get(Tenant, renamed_id)
        renamed_external_id = renamed_tenant.external_id

    # skunkBOX now returns an updated name for the second tenant, a brand
    # new third tenant, and nothing for "Stale Co" (it's simply not on this
    # page/response — not evidence of deletion).
    fake_skunkbox.seed("Old Name Co Renamed", "old-name-co-renamed", external_id=renamed_external_id)
    fake_skunkbox.seed("New From Skunk", "new-from-skunk")

    from app.services.tenant_sync import run_reconciliation
    with full_app.app_context():
        summary = run_reconciliation()

    assert summary["created"] == 1
    assert summary["updated"] == 1
    assert summary["conflicts"] == []
    assert stale_external_id in summary["missing_from_skunkbox"]

    with full_app.app_context():
        # Never deleted.
        stale = db.session.get(Tenant, stale_id)
        assert stale is not None
        assert stale.sync_status == "error"
        assert stale.is_active is True  # flagged, not deactivated

        renamed = db.session.get(Tenant, renamed_id)
        assert renamed.name == "Old Name Co Renamed"
        assert renamed.sync_status == "synced"

        assert Tenant.query.filter_by(name="New From Skunk").one().sync_status == "synced"


def test_reconciliation_skips_flagging_when_remote_response_is_empty(full_app, fake_skunkbox):
    with full_app.app_context():
        tenant_id = create_tenant(full_app, "Untouched Co", "untouched-co")

    from app.services.tenant_sync import run_reconciliation
    with full_app.app_context():
        summary = run_reconciliation()

    assert summary["missing_from_skunkbox"] == []
    with full_app.app_context():
        assert db.session.get(Tenant, tenant_id).sync_status == "synced"


def test_reconciliation_detects_name_conflict_without_overwriting_local(full_app, fake_skunkbox):
    with full_app.app_context():
        local_id = create_tenant(full_app, "Acme", "acme-local")

    # A different remote tenant claims the same (case-insensitive) name.
    fake_skunkbox.seed("acme", "acme-remote")

    from app.services.tenant_sync import run_reconciliation
    with full_app.app_context():
        summary = run_reconciliation()

    assert len(summary["conflicts"]) == 1
    assert summary["conflicts"][0]["code"] == "duplicate_name"
    with full_app.app_context():
        assert Tenant.query.filter(db.func.lower(Tenant.name) == "acme").count() == 1
        assert db.session.get(Tenant, local_id).name == "Acme"


def test_reconciliation_never_reassigns_user_tenant_id(full_app, fake_skunkbox):
    with full_app.app_context():
        advantagefirst = Tenant.query.filter_by(slug="advantagefirst").one()
        fake_skunkbox.seed(
            "AdvantageFirst Renamed", "advantagefirst", external_id=advantagefirst.external_id,
        )
        jane_tenant_id_before = User.query.filter_by(username="jane").one().tenant_id

    from app.services.tenant_sync import run_reconciliation
    with full_app.app_context():
        run_reconciliation()
        jane = User.query.filter_by(username="jane").one()
        assert jane.tenant_id == jane_tenant_id_before


# ── Archived active-tenant fallback via sync ─────────────────────────────────

def test_active_tenant_falls_back_to_cofficiency_when_sync_archives_it(full_app, fake_skunkbox):
    customer_id = create_tenant(full_app, "Fallback Co", "fallback-co")
    with full_app.app_context():
        customer_external_id = db.session.get(Tenant, customer_id).external_id
        fake_skunkbox.seed(
            "Fallback Co", "fallback-co", external_id=customer_external_id, is_active=True,
        )

        admin = User.query.filter_by(username="admin").one()
        admin.last_active_tenant_id = customer_id
        db.session.commit()

    # skunkBOX now reports it archived.
    fake_skunkbox.tenants[customer_external_id]["is_active"] = False

    from app.services.tenant_sync import run_reconciliation
    from app.tenant_context import get_active_tenant
    with full_app.app_context():
        run_reconciliation()
        admin = User.query.filter_by(username="admin").one()
        active = get_active_tenant(admin)
        assert active.slug == "cofficiency"


# ── External users cannot administer/sync tenants ────────────────────────────

def test_external_admin_cannot_manage_or_sync_tenants(full_app, fake_skunkbox):
    """Being an 'admin'-role user of a customer tenant must not grant tenant
    lifecycle access — cofficiency_admin_required checks home-tenant
    identity, not role, precisely to prevent this."""
    customer_id = create_tenant(full_app, "External Admin Co", "external-admin-co")
    create_user(full_app, "ext_admin", customer_id, role="admin")
    _set_password(full_app, "ext_admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "ext_admin", "Test-1234")

    for path, data in [
        ("/tenants/add", {"name": "Should Not Exist"}),
        ("/tenants/sync", {}),
        (f"/tenants/{customer_id}/archive", {}),
    ]:
        resp = client.post(path, data=data, follow_redirects=False)
        assert resp.status_code in (302, 403)

    assert fake_skunkbox.calls == []
    with full_app.app_context():
        assert Tenant.query.filter_by(name="Should Not Exist").first() is None


def test_cofficiency_non_admin_cannot_manage_or_sync_tenants(full_app, fake_skunkbox):
    _ensure_baseline_permissions(full_app, role_name="member")
    with full_app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id
    create_user(full_app, "coffi_member", cofficiency_id, role="member")
    _set_password(full_app, "coffi_member", "Test-1234")
    client = full_app.test_client()
    _login(client, "coffi_member", "Test-1234")

    resp = client.post("/tenants/sync", data={}, follow_redirects=False)
    assert resp.status_code in (302, 403)
    assert fake_skunkbox.calls == []


# ── Active UUID derives server-side, never browser-supplied ────────────────

def test_get_active_tenant_external_id_ignores_request_data(full_app):
    """The resolver takes no request/form/header input at all — proven here
    by calling it directly against a request context that carries a forged
    override and confirming it has no effect on the result."""
    with full_app.app_context():
        advantagefirst_external_id = Tenant.query.filter_by(slug="advantagefirst").one().external_id

    from app.tenant_context import get_active_tenant_external_id

    with full_app.test_request_context(
        "/?tenant_id=99999&external_id=forged-uuid-not-real",
        headers={"X-Tenant-Id": "forged-uuid-not-real"},
    ):
        jane = User.query.filter_by(username="jane").one()
        resolved = get_active_tenant_external_id(jane)

    assert resolved == advantagefirst_external_id
    assert resolved != "forged-uuid-not-real"


def test_require_active_tenant_external_id_raises_when_unavailable(full_app):
    from app.tenant_context import MissingTenantExternalIdError, require_active_tenant_external_id

    with full_app.test_request_context("/"):
        # Anonymous request — no logged-in user, so there is no active tenant.
        with pytest.raises(MissingTenantExternalIdError):
            require_active_tenant_external_id()


# ── Prevent asset/user creation under an unsynchronized or inactive tenant ──

def test_cannot_add_portal_user_when_active_tenant_unsynced(full_app):
    with full_app.app_context():
        tenant = create_tenant(full_app, "Unsynced Co", "unsynced-co")
        t = db.session.get(Tenant, tenant)
        t.sync_status = "unsynced"
        db.session.commit()

        admin = User.query.filter_by(username="admin").one()
        admin.last_active_tenant_id = tenant
        db.session.commit()

    _set_password(full_app, "admin", "Test-1234")
    client = full_app.test_client()
    _login(client, "admin", "Test-1234")

    resp = client.post(
        "/users/add",
        data={"username": "newbie", "email": "newbie@example.com", "password": "Test-1234", "role": "member"},
        follow_redirects=True,
    )
    assert b"not synchronized" in resp.data
    with full_app.app_context():
        assert User.query.filter_by(username="newbie").first() is None
