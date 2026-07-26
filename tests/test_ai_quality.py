"""Phase 7 — Cross-System Tenant AI Assets: Cophy Components, Datasets, and
AI Quality management (docs/prompts/Cross-System Tenant AI Assets - Prompt
- Phase 7 - saas-mortgage.md).

Cophy is a thin proxy over skunkBOX's management API for Components/
Datasets (no local copy of fields/versions/rows); `Experiment` is the one
local row, storing only enough for a history list since skunkBOX has no
`GET /experiments` list endpoint. Uses `fake_skunkbox` throughout — no real
HTTP call is made.
"""
import io

from app.extensions import db
from app.models import Experiment, FeatureFlag, Tenant, TenantFeatureFlag

from .conftest import create_integration, create_tenant, create_user
from .conftest import login as _login
from .conftest import set_password as _set_password


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


# ── Full customer workflow ──────────────────────────────────────────────────

def test_create_and_edit_component_fields_and_prompt(full_app, fake_skunkbox):
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    resp = client.post("/quality/components/add", data={"title": "Income Check", "description": "Verifies income"},
                       follow_redirects=True)
    assert b"Income Check" in resp.data
    with full_app.app_context():
        component_id = list(fake_skunkbox.components.keys())[0]

    resp = client.post(f"/quality/components/{component_id}/save", data={
        "title": "Income Check v2", "description": "Updated", "system_prompt": "Be precise.",
        "prompt": "Extract the applicant's income.", "output_fields": '{"income": "number"}',
    }, follow_redirects=True)
    assert b"saved" in resp.data.lower()

    c = fake_skunkbox.components[component_id]
    assert c["title"] == "Income Check v2"
    assert c["system_prompt"] == "Be precise."
    draft = next(v for v in c["_version_order"] if v["status"] == "draft")
    assert draft["prompt"] == "Extract the applicant's income."


def test_create_draft_version_and_promote_to_release_and_production(full_app, fake_skunkbox):
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    client.post("/quality/components/add", data={"title": "Concierge"}, follow_redirects=True)
    component_id = list(fake_skunkbox.components.keys())[0]

    resp = client.get(f"/quality/components/{component_id}")
    assert b"v1" in resp.data

    client.post(f"/quality/components/{component_id}/promote", data={"target_status": "release"},
               follow_redirects=True)
    versions = fake_skunkbox.components[component_id]["_version_order"]
    assert any(v["status"] == "release" for v in versions)

    client.post(f"/quality/components/{component_id}/promote", data={"target_status": "production"},
               follow_redirects=True)
    versions = fake_skunkbox.components[component_id]["_version_order"]
    assert any(v["status"] == "production" for v in versions)
    assert not any(v["status"] == "release" for v in versions)


def test_create_and_import_dataset(full_app, fake_skunkbox):
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    resp = client.post("/quality/datasets/add", data={"name": "Applications", "dataset_type": "unlabeled"},
                       follow_redirects=True)
    assert b"Applications" in resp.data
    dataset_id = list(fake_skunkbox.datasets.keys())[0]

    csv_bytes = b"income,age\n50000,30\n62000,41\n"
    resp = client.post(
        f"/quality/datasets/{dataset_id}/import",
        data={"file": (io.BytesIO(csv_bytes), "rows.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Imported 2 row" in resp.data
    assert fake_skunkbox.datasets[dataset_id]["current_version"]["row_count"] == 2
    assert fake_skunkbox.datasets[dataset_id]["current_version"]["column_count"] == 2


def test_run_experiment_and_view_quality_metrics_and_results(full_app, fake_skunkbox):
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    client.post("/quality/components/add", data={"title": "Concierge"}, follow_redirects=True)
    component_id = list(fake_skunkbox.components.keys())[0]
    client.post(f"/quality/components/{component_id}/promote", data={"target_status": "release"},
               follow_redirects=True)
    version_id = next(v["id"] for v in fake_skunkbox.components[component_id]["_version_order"]
                      if v["status"] == "release")

    client.post("/quality/datasets/add", data={"name": "Applications"}, follow_redirects=True)
    dataset_id = list(fake_skunkbox.datasets.keys())[0]
    client.post(f"/quality/datasets/{dataset_id}/import",
               data={"file": (io.BytesIO(b"income\n50000\n"), "rows.csv")},
               content_type="multipart/form-data", follow_redirects=True)
    dataset_version_id = fake_skunkbox.datasets[dataset_id]["current_version"]["id"]

    resp = client.get("/quality/experiments/new")
    assert f'value="{version_id}"'.encode() in resp.data
    assert f'value="{dataset_version_id}"'.encode() in resp.data

    resp = client.post("/quality/experiments/new", data={
        "component_version_id": str(version_id), "component_id": str(component_id),
        "dataset_version_id": str(dataset_version_id), "dataset_id": str(dataset_id),
        "model_id": "1",
    }, follow_redirects=True)
    assert resp.status_code == 200

    with full_app.app_context():
        experiment = Experiment.query.one()
    skunkbox_experiment_id = experiment.skunkbox_experiment_id

    # Simulate the run finishing with a result.
    fe = fake_skunkbox.experiments[skunkbox_experiment_id]
    fe["status"] = "completed"
    fe["total_records"] = 1
    fe["processed_records"] = 1
    fe["progress_pct"] = 100
    fe["eval_overall_score"] = 0.92
    fe["_results"] = [{"record_index": 0, "status": "completed",
                       "result_data": {"income": 50000}, "eval_scores": {"overall_score": 0.92},
                       "error_message": None, "latency_ms": 400}]

    resp = client.get(f"/quality/experiments/{experiment.id}")
    assert b"Completed" in resp.data
    assert b"0.92" in resp.data


def test_archive_and_reactivate_component(full_app, fake_skunkbox):
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    client.post("/quality/components/add", data={"title": "Concierge"}, follow_redirects=True)
    component_id = list(fake_skunkbox.components.keys())[0]

    client.post(f"/quality/components/{component_id}/archive", follow_redirects=True)
    assert fake_skunkbox.components[component_id]["is_active"] is False

    client.post(f"/quality/components/{component_id}/reactivate", follow_redirects=True)
    assert fake_skunkbox.components[component_id]["is_active"] is True


# ── Permission / feature-flag denial ────────────────────────────────────────

def test_blocked_when_ai_quality_feature_flag_disabled(full_app, fake_skunkbox):
    """No override applied — the flag defaults to False repo-wide."""
    tenant_id = create_tenant(full_app, "Customer A", "customer-a")
    create_user(full_app, "admin_a", tenant_id, role="admin")
    client = _client_for(full_app, "admin_a")

    resp = client.get("/quality/components", follow_redirects=True)
    assert b"not currently enabled" in resp.data
    assert fake_skunkbox.calls == []


def test_view_only_role_cannot_create_component(full_app, fake_skunkbox):
    from app.models import Permission, Role
    tenant_id, _ = _setup_tenant(full_app, username="unused_admin")
    with full_app.app_context():
        role = Role(name="qa_viewer", is_system=False)
        db.session.add(role)
        db.session.flush()
        from app.page_registry import PAGES
        for page in PAGES:
            # 'dashboard' also gets view access: permission_required's own
            # denial redirect target is main.dashboard, so denying it too
            # would trip a redirect loop rather than exercising the actual
            # components-permission denial this test is after.
            level = "view" if page["slug"] in ("components", "dashboard") else "no_access"
            db.session.add(Permission(role_id=role.id, page_slug=page["slug"], access_level=level))
        db.session.commit()
    create_user(full_app, "viewer_a", tenant_id, role="qa_viewer")
    client = _client_for(full_app, "viewer_a")

    resp = client.post("/quality/components/add", data={"title": "Should Not Exist"}, follow_redirects=True)
    assert b"do not have permission" in resp.data
    assert fake_skunkbox.components == {}


# ── Cross-tenant ids in every mutation/read ─────────────────────────────────

def test_cross_tenant_component_id_404s_on_read_and_every_mutation(full_app, fake_skunkbox):
    tenant_a, _ = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    client_a = _client_for(full_app, "admin_a")
    client_a.post("/quality/components/add", data={"title": "A's Component"}, follow_redirects=True)
    component_id = list(fake_skunkbox.components.keys())[0]

    client_b = _client_for(full_app, "admin_b")
    assert client_b.get(f"/quality/components/{component_id}").status_code == 404
    assert client_b.post(f"/quality/components/{component_id}/save", data={"title": "Hacked"}).status_code == 404
    assert client_b.post(f"/quality/components/{component_id}/archive").status_code == 404
    assert client_b.post(f"/quality/components/{component_id}/promote",
                         data={"target_status": "release"}).status_code == 404
    assert fake_skunkbox.components[component_id]["title"] == "A's Component"
    assert fake_skunkbox.components[component_id]["is_active"] is True


def test_cross_tenant_dataset_id_404s(full_app, fake_skunkbox):
    tenant_a, _ = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    client_a = _client_for(full_app, "admin_a")
    client_a.post("/quality/datasets/add", data={"name": "A's Dataset"}, follow_redirects=True)
    dataset_id = list(fake_skunkbox.datasets.keys())[0]

    client_b = _client_for(full_app, "admin_b")
    assert client_b.get(f"/quality/datasets/{dataset_id}").status_code == 404
    assert client_b.post(f"/quality/datasets/{dataset_id}/archive").status_code == 404
    assert client_b.post(
        f"/quality/datasets/{dataset_id}/import",
        data={"file": (io.BytesIO(b"a\n1\n"), "rows.csv")}, content_type="multipart/form-data",
    ).status_code == 404


def test_cross_tenant_experiment_id_404s(full_app, fake_skunkbox):
    tenant_a, admin_a_id = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    with full_app.app_context():
        experiment = Experiment(
            tenant_id=tenant_a, skunkbox_experiment_id=1, skunkbox_component_id=1,
            skunkbox_component_version_id=1, skunkbox_dataset_id=1, skunkbox_dataset_version_id=1,
            created_by_user_id=admin_a_id,
        )
        db.session.add(experiment)
        db.session.commit()
        experiment_id = experiment.id

    client_b = _client_for(full_app, "admin_b")
    assert client_b.get(f"/quality/experiments/{experiment_id}").status_code == 404
    assert client_b.get(f"/quality/experiments/{experiment_id}/status").status_code == 404


# ── Switching during an open edit or job poll ───────────────────────────────

def test_switching_active_tenant_invalidates_open_experiment_poll(full_app, fake_skunkbox):
    tenant_a, admin_a_id = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")
    with full_app.app_context():
        cofficiency_id = Tenant.query.filter_by(slug="cofficiency").one().id
    create_user(full_app, "coffi_admin", cofficiency_id, role="admin")

    with full_app.app_context():
        tenant_a_ext_id = db.session.get(Tenant, tenant_a).external_id
        experiment = Experiment(
            tenant_id=tenant_a, skunkbox_experiment_id=1, skunkbox_component_id=1,
            skunkbox_component_version_id=1, skunkbox_dataset_id=1, skunkbox_dataset_version_id=1,
            created_by_user_id=admin_a_id,
        )
        db.session.add(experiment)
        db.session.commit()
        experiment_id = experiment.id
    fake_skunkbox.seed_experiment(1, tenant_a_ext_id, status="running")

    client = _client_for(full_app, "coffi_admin")
    client.post("/tenants/switch", data={"tenant_id": tenant_a, "next": "/"}, follow_redirects=True)
    assert client.get(f"/quality/experiments/{experiment_id}/status").status_code == 200

    client.post("/tenants/switch", data={"tenant_id": tenant_b, "next": "/"}, follow_redirects=True)
    assert client.get(f"/quality/experiments/{experiment_id}/status").status_code == 404
    assert client.get(f"/quality/experiments/{experiment_id}").status_code == 404


# ── Idempotent retry ─────────────────────────────────────────────────────────

def test_create_component_and_experiment_send_idempotency_keys(full_app, fake_skunkbox):
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    client.post("/quality/components/add", data={"title": "Concierge"}, follow_redirects=True)
    create_calls = [c for c in fake_skunkbox.calls if c[0] == "create_component"]
    assert len(create_calls) == 1
    assert create_calls[0][2]["idempotency_key"]  # non-empty kwarg

    component_id = list(fake_skunkbox.components.keys())[0]
    client.post(f"/quality/components/{component_id}/promote", data={"target_status": "release"},
               follow_redirects=True)
    promote_calls = [c for c in fake_skunkbox.calls if c[0] == "promote_component_version"]
    assert promote_calls[0][2]["idempotency_key"]


# ── Backend unavailable/timeout behavior ────────────────────────────────────

def test_components_list_shows_safe_error_on_skunkbox_failure(full_app, fake_skunkbox):
    from app.skunkbox_client import SkunkBoxClientError
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")
    fake_skunkbox.fail_next = ("list_components", SkunkBoxClientError("timed out", status_code=None))

    resp = client.get("/quality/components")
    assert resp.status_code == 200
    assert b"Could not load Components" in resp.data


def test_new_experiment_form_shows_safe_error_on_skunkbox_failure(full_app, fake_skunkbox):
    from app.skunkbox_client import SkunkBoxClientError
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")
    fake_skunkbox.fail_next = ("list_components", SkunkBoxClientError("backend unavailable", status_code=502))

    resp = client.get("/quality/experiments/new")
    assert resp.status_code == 200
    assert b"Could not load Components/Datasets" in resp.data


# ── No secret exposure ──────────────────────────────────────────────────────

def test_service_secret_never_rendered_on_any_quality_page(full_app, fake_skunkbox):
    secret = "s3cr3t-should-never-render-anywhere"
    full_app.config["SKUNKBOX_SERVICE_SECRET"] = secret
    _setup_tenant(full_app)
    client = _client_for(full_app, "admin_a")

    client.post("/quality/components/add", data={"title": "Concierge"}, follow_redirects=True)
    component_id = list(fake_skunkbox.components.keys())[0]
    client.post("/quality/datasets/add", data={"name": "Applications"}, follow_redirects=True)

    for resp in (
        client.get("/quality/components"),
        client.get(f"/quality/components/{component_id}"),
        client.get("/quality/datasets"),
        client.get("/quality/experiments/new"),
        client.get("/quality/experiments"),
    ):
        assert secret not in resp.get_data(as_text=True)


# ── No hard-delete/optimizer/internal controls exposed ──────────────────────

def test_no_delete_or_optimizer_routes_exist_under_quality(full_app):
    rules = [r for r in full_app.url_map.iter_rules() if r.rule.startswith("/quality")]
    assert not any("DELETE" in r.methods for r in rules)
    assert not any("optimizer" in r.rule or "delete" in r.rule.lower() for r in rules)


# ── Same-tenant Component/Dataset selection in the Experiment picker ───────

def test_experiment_picker_only_offers_same_tenant_resources(full_app, fake_skunkbox):
    tenant_a, _ = _setup_tenant(full_app, "Customer A", "customer-a", "admin_a")
    tenant_b, _ = _setup_tenant(full_app, "Customer B", "customer-b", "admin_b")

    client_a = _client_for(full_app, "admin_a")
    client_a.post("/quality/components/add", data={"title": "A Only Component"}, follow_redirects=True)
    a_component_id = list(fake_skunkbox.components.keys())[0]
    client_a.post(f"/quality/components/{a_component_id}/promote", data={"target_status": "release"},
                 follow_redirects=True)
    client_a.post("/quality/datasets/add", data={"name": "A Only Dataset"}, follow_redirects=True)
    a_dataset_id = list(fake_skunkbox.datasets.keys())[0]
    client_a.post(f"/quality/datasets/{a_dataset_id}/import",
                 data={"file": (io.BytesIO(b"x\n1\n"), "r.csv")}, content_type="multipart/form-data",
                 follow_redirects=True)

    client_b = _client_for(full_app, "admin_b")
    resp = client_b.get("/quality/experiments/new")
    assert b"A Only Component" not in resp.data
    assert b"A Only Dataset" not in resp.data
