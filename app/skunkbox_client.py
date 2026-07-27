"""Focused HTTP client for skunkBOX's Phase 4 tenant provisioning and
customer management APIs (docs/prompts/Cross-System Tenant AI Assets -
PRD.md §7, §14, §17).

Every cross-system service-credential call goes through here — routes and
CLI commands must never make raw HTTP calls to skunkBOX directly (Phase 5
spec: "Do not scatter raw HTTP calls across routes"). This module is
distinct from the older, unrelated per-tenant `Integration`-based chat/
document API client inlined in app/routes/agents.py, which authenticates
with a per-tenant `X-API-Key` (SkunkApiKey) rather than the service
credential used here — see docs/ARCHITECTURE.md "skunkBOX interim boundary".

Auth: X-Service-Secret (SKUNKBOX_SERVICE_SECRET from config/environment) —
never logged, never rendered in a template or flash message. Tenant
*lifecycle* calls (list/get/create/update/archive/reactivate) are the
provisioning API, which per the Phase 4 contract is not itself
tenant-scoped. Tenant *management* calls (knowledge/agents) additionally
carry X-Tenant-Id — the caller's active tenant UUID, resolved server-side
via tenant_context.require_active_tenant_external_id(), never from request
input — so skunkBOX can apply its owned-or-shared visibility rule.
"""
import logging

import requests
from flask import current_app

log = logging.getLogger(__name__)


class SkunkBoxClientError(Exception):
    """Raised for any failure talking to skunkBOX — network/timeout error or
    a non-2xx response. `status_code` is None for network/timeout failures
    (there was no HTTP response to read a status from)."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


def _base_url() -> str:
    return current_app.config["SKUNKBOX_BASE_URL"].rstrip("/")


def _secret() -> str:
    secret = current_app.config.get("SKUNKBOX_SERVICE_SECRET") or ""
    if not secret:
        raise SkunkBoxClientError("SKUNKBOX_SERVICE_SECRET is not configured.")
    return secret


def _timeout() -> float:
    return current_app.config.get("SKUNKBOX_CLIENT_TIMEOUT", 10)


def _request(method: str, path: str, idempotency_key: str | None = None,
            json_body: dict | None = None, params: dict | None = None,
            retry: bool = False, tenant_id: str | None = None) -> dict:
    """Low-level request helper.

    `retry` (one retry, on network error or 5xx only) is only ever safe for
    read-only calls or writes that carry an idempotency key — callers below
    set it accordingly, never for a bare mutation.

    `tenant_id` is the caller's active tenant UUID (skunkBOX `public_id`),
    sent as X-Tenant-Id for tenant-scoped management calls. Callers must
    pass a value already resolved server-side (never request input).
    """
    url = f"{_base_url()}{path}"
    headers = {"X-Service-Secret": _secret()}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id

    attempts = 2 if retry else 1
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = requests.request(
                method, url, headers=headers, json=json_body, params=params,
                timeout=_timeout(),
            )
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            log.warning(
                "skunkbox_client: %s %s failed (attempt %d/%d) tenant=%s: %s",
                method, path, attempt + 1, attempts, tenant_id or "-", exc.__class__.__name__,
            )
            continue

        if resp.status_code >= 500 and retry and attempt < attempts - 1:
            log.warning("skunkbox_client: %s %s returned %d tenant=%s, retrying once",
                       method, path, resp.status_code, tenant_id or "-")
            continue

        try:
            body = resp.json()
        except ValueError:
            body = {}

        if resp.status_code >= 400:
            raise SkunkBoxClientError(
                body.get("message") or f"skunkBOX returned HTTP {resp.status_code}",
                status_code=resp.status_code, error_code=body.get("error"),
            )
        return body

    raise SkunkBoxClientError(f"skunkBOX request failed: {last_exc}") from last_exc


# ── Tenant lifecycle ─────────────────────────────────────────────────────

def list_tenants(updated_since: str | None = None, limit: int = 200, offset: int = 0) -> dict:
    """GET-only, always safe to retry."""
    params = {"limit": limit, "offset": offset}
    if updated_since:
        params["updated_since"] = updated_since
    return _request("GET", "/api/v1/tenants", params=params, retry=True)


def get_tenant(external_id: str) -> dict:
    return _request("GET", f"/api/v1/tenants/{external_id}", retry=True)


def create_tenant(name: str, idempotency_key: str | None = None) -> dict:
    """Caller should generate and persist one idempotency_key per logical
    creation attempt and reuse it on retry — this function does not invent
    one itself, since a fresh key on every call would defeat the point."""
    return _request(
        "POST", "/api/v1/tenants", json_body={"name": name},
        idempotency_key=idempotency_key, retry=bool(idempotency_key),
    )


def update_tenant(external_id: str, name: str) -> dict:
    return _request("PATCH", f"/api/v1/tenants/{external_id}", json_body={"name": name})


def archive_tenant(external_id: str) -> dict:
    return _request("POST", f"/api/v1/tenants/{external_id}/archive")


def reactivate_tenant(external_id: str) -> dict:
    return _request("POST", f"/api/v1/tenants/{external_id}/reactivate")


# ── Knowledge / Agents management (read-only) ───────────────────────────
#
# Every call here requires the caller's active tenant UUID — skunkBOX
# applies its `tenant_id == caller OR is_shared` visibility rule server-side
# and returns owned-plus-shared records with `is_shared`/`owner`/`can_edit`.
# There is no document-content, search, or download endpoint in this API —
# that remains the older per-tenant `Integration`/X-API-Key path used by
# app/routes/agents.py's Learning Center document routes.

def list_knowledge_collections(tenant_id: str) -> dict:
    """GET-only, always safe to retry. Returns {"collections": [...]}."""
    return _request("GET", "/api/v1/management/knowledge/collections", tenant_id=tenant_id, retry=True)


def get_knowledge_collection(tenant_id: str, collection_id: int) -> dict:
    return _request(
        "GET", f"/api/v1/management/knowledge/collections/{collection_id}",
        tenant_id=tenant_id, retry=True,
    )


def list_agents(tenant_id: str) -> dict:
    """GET-only, always safe to retry. Returns {"agents": [...]}."""
    return _request("GET", "/api/v1/management/agents", tenant_id=tenant_id, retry=True)


def get_agent(tenant_id: str, agent_id: int) -> dict:
    return _request("GET", f"/api/v1/management/agents/{agent_id}", tenant_id=tenant_id, retry=True)


# ── Components / AI Assets (Phase 7) ────────────────────────────────────
#
# skunkBOX enforces tenant ownership server-side on every call below (a
# cross-tenant or nonexistent id both 404 identically, per its "don't
# disclose cross-tenant existence" convention) — this client never
# independently re-checks ownership, it only ever passes through the
# already-server-resolved active tenant UUID.
#
# There is no changelog/history endpoint and no hard-delete/optimizer
# surface in this API — archive/reactivate (soft state only) is the only
# lifecycle mutation besides edit/promote.

def list_components(tenant_id: str, is_active: bool | None = None, limit: int = 20, offset: int = 0) -> dict:
    params = {"limit": limit, "offset": offset}
    if is_active is not None:
        params["is_active"] = int(is_active)
    return _request("GET", "/api/v1/management/components", tenant_id=tenant_id, params=params, retry=True)


def get_component(tenant_id: str, component_id: int) -> dict:
    return _request("GET", f"/api/v1/management/components/{component_id}", tenant_id=tenant_id, retry=True)


def create_component(tenant_id: str, title: str, category_id: int | None = None,
                     description: str | None = None, idempotency_key: str | None = None) -> dict:
    body = {"title": title}
    if category_id is not None:
        body["category_id"] = category_id
    if description is not None:
        body["description"] = description
    return _request(
        "POST", "/api/v1/management/components", tenant_id=tenant_id, json_body=body,
        idempotency_key=idempotency_key, retry=bool(idempotency_key),
    )


def update_component(tenant_id: str, component_id: int, **fields) -> dict:
    """`fields` may include any of: title, description, system_prompt,
    json_schema, json_formatting_requirements, release_notes (component-
    level, always writable) and prompt, output_fields, justification_prompt
    (written to the current draft version — 409 if none exists or it's
    already locked by an Experiment). Only non-None entries are sent."""
    body = {k: v for k, v in fields.items() if v is not None}
    return _request("PATCH", f"/api/v1/management/components/{component_id}", tenant_id=tenant_id, json_body=body)


def list_component_versions(tenant_id: str, component_id: int) -> dict:
    return _request(
        "GET", f"/api/v1/management/components/{component_id}/versions", tenant_id=tenant_id, retry=True,
    )


def promote_component_version(tenant_id: str, component_id: int, target_status: str,
                              idempotency_key: str | None = None) -> dict:
    """`target_status` is "release" or "production". skunkBOX maps every
    promotion-rule violation (no draft, release already exists, etc.) to
    400, not 409 — unlike the plain component PATCH."""
    return _request(
        "POST", f"/api/v1/management/components/{component_id}/promote", tenant_id=tenant_id,
        json_body={"target_status": target_status},
        idempotency_key=idempotency_key, retry=bool(idempotency_key),
    )


def archive_component(tenant_id: str, component_id: int) -> dict:
    return _request("POST", f"/api/v1/management/components/{component_id}/archive", tenant_id=tenant_id)


def reactivate_component(tenant_id: str, component_id: int) -> dict:
    return _request("POST", f"/api/v1/management/components/{component_id}/reactivate", tenant_id=tenant_id)


# ── Datasets (Phase 7) ───────────────────────────────────────────────────
#
# No reactivate-dataset endpoint exists upstream (archive is one-way via
# this API) — do not add one here without confirming skunkBOX has shipped
# it. No row-preview/validation endpoint either: import is atomic
# create-and-commit.

def list_datasets(tenant_id: str, limit: int = 20, offset: int = 0) -> dict:
    return _request(
        "GET", "/api/v1/management/datasets", tenant_id=tenant_id,
        params={"limit": limit, "offset": offset}, retry=True,
    )


def get_dataset(tenant_id: str, dataset_id: int) -> dict:
    return _request("GET", f"/api/v1/management/datasets/{dataset_id}", tenant_id=tenant_id, retry=True)


def create_dataset(tenant_id: str, name: str, description: str | None = None,
                   dataset_type: str = "unlabeled", idempotency_key: str | None = None) -> dict:
    body = {"name": name, "dataset_type": dataset_type}
    if description is not None:
        body["description"] = description
    return _request(
        "POST", "/api/v1/management/datasets", tenant_id=tenant_id, json_body=body,
        idempotency_key=idempotency_key, retry=bool(idempotency_key),
    )


def update_dataset(tenant_id: str, dataset_id: int, name: str | None = None,
                   description: str | None = None) -> dict:
    body = {k: v for k, v in {"name": name, "description": description}.items() if v is not None}
    return _request("PATCH", f"/api/v1/management/datasets/{dataset_id}", tenant_id=tenant_id, json_body=body)


def import_dataset_rows(tenant_id: str, dataset_id: int, rows: list) -> dict:
    """No Idempotency-Key support upstream — a dropped connection can
    duplicate a DatasetVersion; callers should not blindly auto-retry this
    one the way they safely can for the idempotency-keyed calls above."""
    return _request(
        "POST", f"/api/v1/management/datasets/{dataset_id}/import", tenant_id=tenant_id,
        json_body={"rows": rows},
    )


def archive_dataset(tenant_id: str, dataset_id: int) -> dict:
    return _request("POST", f"/api/v1/management/datasets/{dataset_id}/archive", tenant_id=tenant_id)


# ── Experiments (Phase 7) ────────────────────────────────────────────────
#
# No list endpoint exists upstream — app/models.py's local `Experiment` row
# exists solely so Cophy can show a history list; every other detail here
# (status/results/metrics) is always live-fetched by skunkbox_experiment_id,
# never cached locally.

def create_experiment(tenant_id: str, component_version_id: int, dataset_version_id: int,
                      model_id: int, description: str | None = None,
                      idempotency_key: str | None = None) -> dict:
    """skunkBOX validates, in order: component_version_id belongs to this
    tenant and is status release/production (400 invalid_component_version
    otherwise); dataset_version_id belongs to this tenant; model_id is a
    valid active model. Each mismatch/not-found is its own error code —
    see SkunkBoxClientError.error_code on failure."""
    body = {
        "component_version_id": component_version_id,
        "dataset_version_id": dataset_version_id,
        "model_id": model_id,
    }
    if description is not None:
        body["description"] = description
    return _request(
        "POST", "/api/v1/management/experiments", tenant_id=tenant_id, json_body=body,
        idempotency_key=idempotency_key, retry=bool(idempotency_key),
    )


def get_experiment(tenant_id: str, experiment_id: int) -> dict:
    return _request("GET", f"/api/v1/management/experiments/{experiment_id}", tenant_id=tenant_id, retry=True)


def get_experiment_results(tenant_id: str, experiment_id: int, limit: int = 50, offset: int = 0) -> dict:
    return _request(
        "GET", f"/api/v1/management/experiments/{experiment_id}/results", tenant_id=tenant_id,
        params={"limit": limit, "offset": offset}, retry=True,
    )
