"""Customer-facing Components (AI Assets), Datasets, and Experiments/AI
Quality — Cross-System Tenant AI Assets PRD Phase 7.

Cophy is a thin proxy over skunkBOX's Phase 4 management API
(app/skunkbox_client.py) for Components and Datasets: no local copy of
fields/versions/rows is kept, and every resource id from the URL is passed
straight through with the server-resolved active tenant UUID — skunkBOX
independently re-validates ownership and 404s a cross-tenant or forged id,
Cophy never trusts the id itself. Experiments are the one exception: since
skunkBOX's management API has no list endpoint, `models.Experiment` stores
just enough (skunkbox ids) to build a history list — status/results/metrics
are always live-fetched, never cached (see models.Experiment's docstring).
"""
import csv
import io
import uuid

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..access import feature_required, permission_required
from ..activity_logger import log_activity
from ..extensions import db
from ..models import Experiment
from ..skunkbox_client import SkunkBoxClientError
from ..tenant_context import (MissingTenantExternalIdError, get_active_tenant,
                              require_active_tenant_external_id, require_tenant_record)

quality_bp = Blueprint("quality", __name__, url_prefix="/quality")

_MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_IMPORT_ROWS = 5000


def _tenant_ext_id_or_flash():
    """Resolve the active tenant's skunkBOX UUID, or flash a safe error and
    return None. Every mutating/reading route below bails out the same way
    on a missing/unsynced tenant rather than risking a raw 500."""
    try:
        return require_active_tenant_external_id()
    except MissingTenantExternalIdError:
        flash("This workspace is not yet synchronized with skunkBOX. Run tenant reconciliation and try again.",
             "error")
        return None


def _handle_skunkbox_error(exc: SkunkBoxClientError):
    flash(f"skunkBOX error: {exc}", "error")


# ─────────────────────────────────────────────────────────────────────────────
# Components / AI Assets
# ─────────────────────────────────────────────────────────────────────────────

@quality_bp.route("/components")
@login_required
@permission_required("components", "view")
@feature_required("ai_quality")
def list_components():
    ext_id = _tenant_ext_id_or_flash()
    components, error = [], None
    show_archived = request.args.get("show_archived") == "1"

    if ext_id:
        from .. import skunkbox_client
        try:
            data = skunkbox_client.list_components(
                ext_id, is_active=(None if show_archived else True), limit=100, offset=0,
            )
            components = data.get("components", [])
        except SkunkBoxClientError as exc:
            error = str(exc)
        except Exception as exc:
            error = str(exc)

    return render_template(
        "quality/components_list.html",
        components=components, error=error, show_archived=show_archived,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "AI Assets", "url": None},
        ],
    )


@quality_bp.route("/components/add", methods=["GET", "POST"])
@login_required
@permission_required("components", "edit")
@feature_required("ai_quality")
def add_component():
    if request.method == "POST":
        ext_id = _tenant_ext_id_or_flash()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip() or None
        if not title:
            flash("Title is required.", "error")
            return redirect(url_for("quality.add_component"))
        if ext_id:
            from .. import skunkbox_client
            try:
                result = skunkbox_client.create_component(
                    ext_id, title, description=description, idempotency_key=str(uuid.uuid4()),
                )
                log_activity(current_user, "component.created", page="AI Assets")
                flash(f"Component '{title}' created.", "success")
                return redirect(url_for("quality.view_component", component_id=result["id"]))
            except SkunkBoxClientError as exc:
                _handle_skunkbox_error(exc)
        return redirect(url_for("quality.add_component"))

    return render_template(
        "quality/component_add.html",
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "AI Assets", "url": url_for("quality.list_components")},
            {"label": "New Component", "url": None},
        ],
    )


@quality_bp.route("/components/<int:component_id>")
@login_required
@permission_required("components", "view")
@feature_required("ai_quality")
def view_component(component_id):
    ext_id = _tenant_ext_id_or_flash()
    component, error = None, None
    if ext_id:
        from .. import skunkbox_client
        try:
            component = skunkbox_client.get_component(ext_id, component_id)
        except SkunkBoxClientError as exc:
            if exc.status_code == 404:
                abort(404)
            error = str(exc)

    return render_template(
        "quality/component_detail.html",
        component=component, component_id=component_id, error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "AI Assets", "url": url_for("quality.list_components")},
            {"label": component["title"] if component else f"Component {component_id}", "url": None},
        ],
    )


@quality_bp.route("/components/<int:component_id>/save", methods=["POST"])
@login_required
@permission_required("components", "edit")
@feature_required("ai_quality")
def save_component(component_id):
    ext_id = _tenant_ext_id_or_flash()
    if not ext_id:
        return redirect(url_for("quality.view_component", component_id=component_id))

    fields = {}
    for key in ("title", "description", "system_prompt", "json_schema",
               "json_formatting_requirements", "release_notes",
               "prompt", "output_fields", "justification_prompt"):
        value = request.form.get(key)
        if value is not None:
            fields[key] = value.strip() or None

    from .. import skunkbox_client
    try:
        skunkbox_client.update_component(ext_id, component_id, **fields)
        log_activity(current_user, "component.updated", page="AI Assets")
        flash("Component saved.", "success")
    except SkunkBoxClientError as exc:
        if exc.status_code == 404:
            abort(404)
        _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_component", component_id=component_id))


@quality_bp.route("/components/<int:component_id>/promote", methods=["POST"])
@login_required
@permission_required("components", "edit")
@feature_required("ai_quality")
def promote_component(component_id):
    ext_id = _tenant_ext_id_or_flash()
    if not ext_id:
        return redirect(url_for("quality.view_component", component_id=component_id))

    target_status = request.form.get("target_status", "").strip()
    if target_status not in ("release", "production"):
        flash("Invalid promotion target.", "error")
        return redirect(url_for("quality.view_component", component_id=component_id))

    from .. import skunkbox_client
    try:
        skunkbox_client.promote_component_version(
            ext_id, component_id, target_status, idempotency_key=str(uuid.uuid4()),
        )
        log_activity(current_user, "component.promoted", page="AI Assets")
        flash(f"Component promoted to {target_status}.", "success")
    except SkunkBoxClientError as exc:
        if exc.status_code == 404:
            abort(404)
        _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_component", component_id=component_id))


@quality_bp.route("/components/<int:component_id>/archive", methods=["POST"])
@login_required
@permission_required("components", "edit")
@feature_required("ai_quality")
def archive_component(component_id):
    ext_id = _tenant_ext_id_or_flash()
    if ext_id:
        from .. import skunkbox_client
        try:
            skunkbox_client.archive_component(ext_id, component_id)
            log_activity(current_user, "component.archived", page="AI Assets")
            flash("Component archived.", "success")
        except SkunkBoxClientError as exc:
            if exc.status_code == 404:
                abort(404)
            _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_component", component_id=component_id))


@quality_bp.route("/components/<int:component_id>/reactivate", methods=["POST"])
@login_required
@permission_required("components", "edit")
@feature_required("ai_quality")
def reactivate_component(component_id):
    ext_id = _tenant_ext_id_or_flash()
    if ext_id:
        from .. import skunkbox_client
        try:
            skunkbox_client.reactivate_component(ext_id, component_id)
            log_activity(current_user, "component.reactivated", page="AI Assets")
            flash("Component reactivated.", "success")
        except SkunkBoxClientError as exc:
            if exc.status_code == 404:
                abort(404)
            _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_component", component_id=component_id))


# ─────────────────────────────────────────────────────────────────────────────
# Datasets
# ─────────────────────────────────────────────────────────────────────────────

@quality_bp.route("/datasets")
@login_required
@permission_required("datasets", "view")
@feature_required("ai_quality")
def list_datasets():
    ext_id = _tenant_ext_id_or_flash()
    datasets, error = [], None
    if ext_id:
        from .. import skunkbox_client
        try:
            data = skunkbox_client.list_datasets(ext_id, limit=100, offset=0)
            datasets = data.get("datasets", [])
        except SkunkBoxClientError as exc:
            error = str(exc)
        except Exception as exc:
            error = str(exc)

    return render_template(
        "quality/datasets_list.html",
        datasets=datasets, error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Datasets", "url": None},
        ],
    )


@quality_bp.route("/datasets/add", methods=["GET", "POST"])
@login_required
@permission_required("datasets", "edit")
@feature_required("ai_quality")
def add_dataset():
    if request.method == "POST":
        ext_id = _tenant_ext_id_or_flash()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip() or None
        dataset_type = request.form.get("dataset_type", "unlabeled")
        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("quality.add_dataset"))
        if ext_id:
            from .. import skunkbox_client
            try:
                result = skunkbox_client.create_dataset(
                    ext_id, name, description=description, dataset_type=dataset_type,
                    idempotency_key=str(uuid.uuid4()),
                )
                log_activity(current_user, "dataset.created", page="Datasets")
                flash(f"Dataset '{name}' created.", "success")
                return redirect(url_for("quality.view_dataset", dataset_id=result["id"]))
            except SkunkBoxClientError as exc:
                _handle_skunkbox_error(exc)
        return redirect(url_for("quality.add_dataset"))

    return render_template(
        "quality/dataset_add.html",
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Datasets", "url": url_for("quality.list_datasets")},
            {"label": "New Dataset", "url": None},
        ],
    )


@quality_bp.route("/datasets/<int:dataset_id>")
@login_required
@permission_required("datasets", "view")
@feature_required("ai_quality")
def view_dataset(dataset_id):
    ext_id = _tenant_ext_id_or_flash()
    dataset, error = None, None
    if ext_id:
        from .. import skunkbox_client
        try:
            dataset = skunkbox_client.get_dataset(ext_id, dataset_id)
        except SkunkBoxClientError as exc:
            if exc.status_code == 404:
                abort(404)
            error = str(exc)

    return render_template(
        "quality/dataset_detail.html",
        dataset=dataset, dataset_id=dataset_id, error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Datasets", "url": url_for("quality.list_datasets")},
            {"label": dataset["name"] if dataset else f"Dataset {dataset_id}", "url": None},
        ],
    )


@quality_bp.route("/datasets/<int:dataset_id>/save", methods=["POST"])
@login_required
@permission_required("datasets", "edit")
@feature_required("ai_quality")
def save_dataset(dataset_id):
    ext_id = _tenant_ext_id_or_flash()
    if ext_id:
        name = request.form.get("name", "").strip() or None
        description = request.form.get("description", "").strip() or None
        from .. import skunkbox_client
        try:
            skunkbox_client.update_dataset(ext_id, dataset_id, name=name, description=description)
            log_activity(current_user, "dataset.updated", page="Datasets")
            flash("Dataset saved.", "success")
        except SkunkBoxClientError as exc:
            if exc.status_code == 404:
                abort(404)
            _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))


@quality_bp.route("/datasets/<int:dataset_id>/import", methods=["POST"])
@login_required
@permission_required("datasets", "edit")
@feature_required("ai_quality")
def import_dataset(dataset_id):
    """Cophy parses the uploaded CSV server-side and relays it to skunkBOX
    as the row-JSON body its import endpoint actually expects (there is no
    multipart/file-upload import endpoint upstream) — the service secret
    never reaches the browser, only the parsed row count comes back."""
    ext_id = _tenant_ext_id_or_flash()
    if not ext_id:
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))
    if not file.filename.lower().endswith(".csv"):
        flash("Only .csv files are supported.", "error")
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))

    raw = file.read()
    if len(raw) > _MAX_IMPORT_BYTES:
        flash("File exceeds the 10 MB limit.", "error")
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))

    try:
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error) as exc:
        flash(f"Could not parse CSV: {exc}", "error")
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))

    if not rows:
        flash("The CSV file has no data rows.", "error")
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))
    if len(rows) > _MAX_IMPORT_ROWS:
        flash(f"The CSV file has {len(rows)} rows — the limit is {_MAX_IMPORT_ROWS}.", "error")
        return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))

    from .. import skunkbox_client
    try:
        skunkbox_client.import_dataset_rows(ext_id, dataset_id, rows)
        log_activity(current_user, "dataset.imported", page="Datasets")
        flash(f"Imported {len(rows)} row{'s' if len(rows) != 1 else ''}.", "success")
    except SkunkBoxClientError as exc:
        if exc.status_code == 404:
            abort(404)
        _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))


@quality_bp.route("/datasets/<int:dataset_id>/archive", methods=["POST"])
@login_required
@permission_required("datasets", "edit")
@feature_required("ai_quality")
def archive_dataset(dataset_id):
    ext_id = _tenant_ext_id_or_flash()
    if ext_id:
        from .. import skunkbox_client
        try:
            skunkbox_client.archive_dataset(ext_id, dataset_id)
            log_activity(current_user, "dataset.archived", page="Datasets")
            flash("Dataset archived.", "success")
        except SkunkBoxClientError as exc:
            if exc.status_code == 404:
                abort(404)
            _handle_skunkbox_error(exc)
    return redirect(url_for("quality.view_dataset", dataset_id=dataset_id))


# ─────────────────────────────────────────────────────────────────────────────
# Experiments / AI Quality
# ─────────────────────────────────────────────────────────────────────────────

@quality_bp.route("/experiments")
@login_required
@permission_required("experiments", "view")
@feature_required("ai_quality")
def list_experiments():
    active_tenant = get_active_tenant()
    active_tenant_id = active_tenant.id if active_tenant else None
    experiments = (
        Experiment.query.filter_by(tenant_id=active_tenant_id)
        .order_by(Experiment.created_at.desc()).all()
    )
    return render_template(
        "quality/experiments_list.html",
        experiments=experiments,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "AI Quality", "url": None},
        ],
    )


@quality_bp.route("/experiments/new", methods=["GET", "POST"])
@login_required
@permission_required("experiments", "edit")
@feature_required("ai_quality")
def new_experiment():
    ext_id = _tenant_ext_id_or_flash()
    active_tenant = get_active_tenant()

    if request.method == "POST":
        if not ext_id:
            return redirect(url_for("quality.new_experiment"))
        try:
            component_id = int(request.form.get("component_id", ""))
            component_version_id = int(request.form.get("component_version_id", ""))
            dataset_id = int(request.form.get("dataset_id", ""))
            dataset_version_id = int(request.form.get("dataset_version_id", ""))
            model_id = int(request.form.get("model_id", ""))
        except (TypeError, ValueError):
            flash("Select a component version, a dataset with an imported version, and a model.", "error")
            return redirect(url_for("quality.new_experiment"))
        description = request.form.get("description", "").strip() or None

        from .. import skunkbox_client
        try:
            result = skunkbox_client.create_experiment(
                ext_id, component_version_id, dataset_version_id, model_id,
                description=description, idempotency_key=str(uuid.uuid4()),
            )
        except SkunkBoxClientError as exc:
            _handle_skunkbox_error(exc)
            return redirect(url_for("quality.new_experiment"))

        experiment = Experiment(
            tenant_id=active_tenant.id, skunkbox_experiment_id=result["id"],
            skunkbox_component_id=component_id, skunkbox_component_version_id=component_version_id,
            skunkbox_dataset_id=dataset_id, skunkbox_dataset_version_id=dataset_version_id,
            description=description, created_by_user_id=current_user.id,
        )
        db.session.add(experiment)
        db.session.commit()
        log_activity(current_user, "experiment.started", page="AI Quality")
        flash("Experiment started.", "success")
        return redirect(url_for("quality.view_experiment", experiment_id=experiment.id))

    components, datasets, error = [], [], None
    if ext_id:
        from .. import skunkbox_client
        try:
            components_data = skunkbox_client.list_components(ext_id, is_active=True, limit=100)
            datasets_data = skunkbox_client.list_datasets(ext_id, limit=100)
            # Only components with at least one release/production version,
            # and only datasets with an imported (current) version, are
            # eligible — skunkBOX would reject the rest anyway (400
            # invalid_component_version / no dataset_version_id to send).
            for c in components_data.get("components", []):
                c["eligible_versions"] = [
                    v for v in c.get("versions", []) if v["status"] in ("release", "production")
                ]
            components = [c for c in components_data.get("components", []) if c["eligible_versions"]]
            datasets = [d for d in datasets_data.get("datasets", []) if d.get("current_version")]
        except SkunkBoxClientError as exc:
            error = str(exc)
        except Exception as exc:
            error = str(exc)

    return render_template(
        "quality/experiment_new.html",
        components=components, datasets=datasets, error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "AI Quality", "url": url_for("quality.list_experiments")},
            {"label": "New Experiment", "url": None},
        ],
    )


@quality_bp.route("/experiments/<int:experiment_id>")
@login_required
@permission_required("experiments", "view")
@feature_required("ai_quality")
def view_experiment(experiment_id):
    experiment = db.get_or_404(Experiment, experiment_id)
    require_tenant_record(experiment)

    ext_id = _tenant_ext_id_or_flash()
    skunkbox_experiment, results, error = None, [], None
    if ext_id:
        from .. import skunkbox_client
        try:
            data = skunkbox_client.get_experiment_results(ext_id, experiment.skunkbox_experiment_id)
            skunkbox_experiment = data.get("experiment")
            results = data.get("results", [])
        except SkunkBoxClientError as exc:
            error = str(exc)

    return render_template(
        "quality/experiment_detail.html",
        experiment=experiment, skunkbox_experiment=skunkbox_experiment, results=results, error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "AI Quality", "url": url_for("quality.list_experiments")},
            {"label": f"Experiment #{experiment.id}", "url": None},
        ],
    )


@quality_bp.route("/experiments/<int:experiment_id>/status")
@login_required
@permission_required("experiments", "view")
@feature_required("ai_quality")
def experiment_status(experiment_id):
    """Lightweight JSON poll target. Re-derives the active tenant from the
    server-side session on every call and re-checks local ownership — a
    tenant switch mid-poll naturally 404s on the next tick rather than
    keeping a stale previous-tenant status visible."""
    experiment = db.session.get(Experiment, experiment_id)
    from ..tenant_context import get_active_tenant_id
    if not experiment or experiment.tenant_id != get_active_tenant_id():
        return jsonify({"ok": False, "error": "Not found"}), 404

    try:
        ext_id = require_active_tenant_external_id()
    except MissingTenantExternalIdError:
        return jsonify({"ok": False, "error": "Workspace not synchronized"}), 409

    from .. import skunkbox_client
    try:
        data = skunkbox_client.get_experiment(ext_id, experiment.skunkbox_experiment_id)
    except SkunkBoxClientError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    return jsonify({"ok": True, "experiment": data})
