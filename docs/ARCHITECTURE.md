# Architecture

## Overview

`saas-mortgage` is a monolithic Flask application designed as a reusable foundation for future SaaS prototypes.

## Core stack

- Frontend: HTML, Jinja templates, lightweight CSS
- Backend: Python Flask
- Database: SQLite via SQLAlchemy
- Auth: Flask-Login
- Migrations: Flask-Migrate

## CSRF protection

All browser-originated state changes are protected centrally by
Flask-WTF's `CSRFProtect`, initialized in `app/__init__.py` from the shared
instance in `app/extensions.py`. Server-rendered mutation forms include a
`csrf_token` hidden field. `app/templates/base.html` and the standalone
login page also expose the session-bound token in a `csrf-token` meta tag;
`app/static/js/csrf.js` adds the `X-CSRFToken` header to same-origin
`POST`, `PUT`, `PATCH`, and `DELETE` `fetch()` requests and supplies a
hidden field for dynamically-created forms.

Missing, invalid, and expired tokens fail before route code can mutate
state. Traditional form failures redirect only to a safe same-origin GET
page and show a generic retry message; AJAX/JSON failures return a generic
400 JSON response. No tenant identifier, credential, or application secret
is embedded in the CSRF token. The Client Portal currently has no inbound
machine-to-machine mutation endpoint, so there are no CSRF exemptions.
Outbound calls to skunkBOX use their own service/API credentials and are
not browser endpoints.

CSRF verification is additive to authentication, role permissions, feature
flags, and tenant ownership checks. Passing a valid CSRF token never grants
access to a different tenant's record.

## Design intent

- Keep the starter small enough to understand quickly.
- Preserve the reusable admin core from skunkBOX.
- Make domain-specific features additive rather than embedded in the template.

## Tenant isolation

The app is multi-tenant: one deployment serves Cofficiency (the protected
internal tenant) and any number of customer tenants (POC/prototype
workspaces), with each tenant's data invisible to the others. See
`docs/prompts/Tenant Separation - PRD.md` for the full product spec and
`docs/TENANT_ISOLATION_AUDIT.md` for the implementation audit.

### Home tenant vs. active tenant

- **Home tenant** (`User.tenant_id`) — the tenant a user was created in.
  Immutable after creation by any route; correcting it requires a controlled
  data migration, not ordinary UI.
- **Active tenant** — the tenant workspace a request actually operates
  against. For an external user (home tenant ≠ Cofficiency) these are always
  identical — external users can't switch. For a Cofficiency user, the active
  tenant is their remembered `User.last_active_tenant_id`, falling back to
  Cofficiency if that tenant is missing, invalid, or archived.
- The only place this is resolved is `app/tenant_context.py`
  (`get_active_tenant`, `get_active_tenant_id`, `is_cofficiency_user`,
  `can_switch_tenants`, `require_tenant_record`). Routes and templates call
  into it rather than inventing tenant-selection logic; the resolution is
  cached once per request via `flask.g`.
- Switching (`POST /tenants/switch`) only ever writes
  `last_active_tenant_id`. No route writes `User.tenant_id`.

### Model ownership

| Tenant-owned (required `tenant_id`) | Global |
|---|---|
| `User` (home tenant only) | `Role`, `Permission` |
| `LlmModel`, `Attribute`, `Integration`, `AiAgent` | `NavSection`, `NavItem` |
| `AgentConversation` (children `AgentMessage`/`MessageAttachment` inherit via parent) | `DocPrompt` |
| `LlmRequestLog`, `UserActivityLog`, `ApiRequestLog` (event-time tenant, not necessarily the actor's home tenant) | `ReleaseNote` |
| `TenantFeatureFlag` (override only — `FeatureFlag` catalogue rows are global) | `Tenant` itself |

Uniqueness that used to be global is now tenant-relative:
`LlmModel(tenant_id, name)`, `Attribute(tenant_id, category, name)`,
`Integration(tenant_id, name)`. `User.username`/`User.email` and
`Tenant.name`/`Tenant.slug` remain globally unique — login identity is global.

### Authorization pattern

Tenant enforcement is additive to the existing role/permission system, never
a replacement for it:

```text
authenticated AND existing page/action permission AND record.tenant_id == active_tenant.id
```

- Every tenant-owned list query filters by the active tenant.
- Every create sets `tenant_id` from the server-resolved active tenant —
  never from a client-supplied field.
- Every direct-ID route (edit/toggle/save/delete) calls
  `tenant_context.require_tenant_record(record)` immediately after fetching,
  before reading or mutating anything else; it aborts with 404 on a
  cross-tenant ID rather than 403, so a guessed ID doesn't confirm existence.
- Related records are validated to share a tenant at write time (e.g. an
  `AiAgent` can only reference an `Integration` in the same tenant) rather
  than trusting the relationship was always created correctly.
- Bulk update/delete operations include a tenant predicate even where a
  single-record ID alone couldn't cross tenants, for defense in depth.
- No global SQLAlchemy query hook is used. Every filter is an explicit
  predicate or a call to a small shared helper
  (`tenant_context.get_active_tenant_id()`, `require_tenant_record()`,
  `feature_flags.effective_feature_flags()`) — deliberately, so isolation
  logic stays auditable per call site rather than implicit.
- A Cofficiency user switching tenants gains workspace *selection*, never
  elevated permissions — existing role/permission checks still gate every
  action inside the newly-active tenant.
- Per-tenant feature overrides (`TenantFeatureFlag`) are resolved through
  `app/feature_flags.py`; a disabled feature is enforced at the route level
  via `access.feature_required(key)`, not just by hiding its nav item.

### What "Shared" means (read this before touching any Shared-related code)

**Shared always means "Cofficiency-owned and read/use-only for every other
tenant" — never joint ownership, never editable by the tenant using it,
never a merge of two tenants' data.** A knowledge collection or Agent has
exactly one owner (`tenant_id`), which for a Shared resource is always
Cofficiency; `is_shared=true` grants every *other* active tenant read/use
access to that one Cofficiency-owned row, it does not create a second
owner or a copy. Concretely in this codebase:
- A Shared `AiAgent` mirror row (`is_shared=True`) is a **per-tenant,
  read-only pointer** to a Cofficiency Persona — each tenant that uses it
  gets its own local row (so conversations/FKs work normally), but none of
  those rows are editable, and none of them make the underlying skunkBOX
  Persona jointly owned.
- A Shared knowledge collection's documents are never copied into a
  tenant's own collection — a document has exactly one collection, full
  stop (PRD §10.2); "using" a Shared collection means reading it live from
  skunkBOX, not acquiring a copy.
- Mutating a Shared resource on behalf of a customer is refused everywhere
  in this repo, and independently refused by skunkBOX itself — see
  `docs/TENANT_ISOLATION_AUDIT.md`'s Cross-System section for the specific
  code paths and tests.

### skunkBOX interim boundary

For chat, attachments, and Learning Center/knowledge-base calls, skunkBOX
still does not accept a tenant ID. Isolation there is indirect: each tenant
has its own `Integration` credentials, and `AiAgent`s reference only
same-tenant integrations. Every such call resolves its integration through
the active tenant (or the owning conversation's tenant) before making the
outbound request — a cross-tenant integration/agent reference is rejected
locally first. No speculative tenant field is sent to skunkBOX for these
calls.

Tenant *lifecycle* is a separate, already-solved boundary (Cross-System
Tenant AI Assets PRD, Phase 4/5): skunkBOX is authoritative for tenant
create/edit/archive/reactivate, and Cophy's `Tenant` table is a local mirror
keyed by immutable UUID (`Tenant.external_id`, mapping to skunkBOX's
`Tenant.public_id`). See `app/skunkbox_client.py` (the service-credential
HTTP client), `app/services/tenant_sync.py` (upsert-by-UUID and
reconciliation), and `app/routes/tenants.py` (skunkBOX-first lifecycle
routes — no local-only mutation path). `flask sync-tenants` (`app/cli.py`)
and the in-app "Sync with skunkBOX" button share the same reconciliation
logic. A tenant with `sync_status != "synced"` cannot be used to create new
portal users or AI agents (`app/routes/users.py:add_user`,
`app/routes/models.py:add_agent`) — see `Tenant.sync_status`.

`app/tenant_context.py` provides `get_active_tenant_external_id()` /
`require_active_tenant_external_id()` as the sanctioned way to resolve the
active tenant's skunkBOX UUID: always server-side, from the already-resolved
active tenant, never from a request header, form field, or query string.

Phase 6 is the first consumer of that plumbing: `app/skunkbox_client.py`'s
`list_knowledge_collections()` / `get_knowledge_collection()` /
`list_agents()` / `get_agent()` call skunkBOX's Phase 4 management API
(`GET /api/v1/management/knowledge/collections`, `GET
/api/v1/management/agents`, service credential + `X-Tenant-Id`) to list
records the active tenant may see — its own plus Cofficiency's Shared
knowledge collections/Agents (`is_shared`/`owner`/`can_edit` in the
response; skunkBOX enforces the `tenant_id == caller OR is_shared`
visibility rule server-side, Cophy does not re-derive it). This is a
**second, disjoint skunkBOX auth path** layered on top of the one described
above — `app/routes/agents.py`'s Learning Center document
listing/detail/download and the chat API still use the older per-tenant
`Integration`/`X-API-Key` path, since the Phase 4 management API has no
document-content, search, or download endpoint. A single Learning Center
page load therefore calls skunkBOX twice, once under each credential
scheme: the management API for the clean collection list/labels, the old
API for the actual documents.

`app/services/agent_sync.py`'s `sync_shared_agents_for_tenant()` upserts a
local `AiAgent` mirror row (`is_shared=True`) per Cofficiency Shared Agent
visible to a tenant, run inline on every `list_conversations()` view — the
same "always live, no scheduled job" approach Learning Center already used
for documents, rather than a new reconciliation command. The mirror's
`tenant_id` is the *customer* tenant using it (not Cofficiency), and it
points at that tenant's own "AI Agents" `Integration` — so starting a
conversation with a Shared Agent needs no special-casing anywhere in the
existing conversation code: `AgentConversation.tenant_id` and the outbound
chat call's credentials are already correct by construction. A
`(tenant_id, skunkbox_agent_id)` uniqueness constraint on `ai_agent` (Phase
6 migration) prevents a customer admin from hand-creating a second local
row for a `skunkbox_agent_id` already mirrored — the "no ambiguous
duplicate local ownership" requirement. A Shared mirror can never be
edited/deactivated through the admin UI (`app/routes/models.py`
`save_agent`/`toggle_agent` reject it); it's deactivated, never deleted,
when `sync_shared_agents_for_tenant()` next runs and the Agent is no longer
visible (unshared, archived).

### Customer Agent configuration

skunkBOX Personas are authoritative for Agent fields, lifecycle, and
knowledge associations. Cophy retains the mixed local-pointer model because
conversations and chat Integrations require a local `AiAgent`:
`is_shared=False` is tenant-owned and `is_shared=True` is a per-tenant,
read-only pointer to a Cofficiency Shared Persona. The unique
`(tenant_id, skunkbox_agent_id)` key remains; reconciliation updates owned
and Shared pointers but never changes ownership type or deletes history.

System Config mutations and collection replacement go through
`app/skunkbox_client.py`. Eligible collections are returned by skunkBOX
(tenant-owned plus Cofficiency Shared); Cophy derives the tenant UUID
server-side and does not duplicate eligibility rules. Shared Agents expose
no mutation, Shared-toggle, or hard-delete control.

Every service-credential call writes a local `ApiRequestLog` with active
tenant, operation/endpoint, target ID, status, latency, and returned
correlation ID. Credentials and bodies are never stored. Audit failure is
non-blocking in production and raised during tests.

Phase 7 extends the same management-API path to Components (AI Assets),
Datasets, and Experiments — `app/routes/quality.py` (blueprint `quality_bp`,
`/quality/*`). Components and Datasets follow Learning Center's "thin proxy,
no local copy" pattern exactly: every field, version, and row lives only in
skunkBOX, fetched fresh on each request via `require_active_tenant_external_id()`.
Every resource id from the URL passes straight through to
`app/skunkbox_client.py`, which sends it with the server-resolved tenant
UUID; skunkBOX independently re-validates ownership and 404s a cross-tenant
or forged id identically to a nonexistent one, and Cophy never second-guesses
that with its own ownership check.

`Experiment` is the one local table in this phase, and it exists only
because skunkBOX's Phase 4 management API has no `GET /experiments` list
endpoint — there is no other way to show a history list. It stores just
enough to resolve back to skunkBOX (`skunkbox_experiment_id`,
`skunkbox_component_id`/`skunkbox_component_version_id`,
`skunkbox_dataset_id`/`skunkbox_dataset_version_id`) plus who started it and
when; status, progress, and results are always live-fetched by
`skunkbox_experiment_id`, never cached, per the PRD's "do not recreate ...
evaluation state machines locally." The experiment status-poll endpoint
(`/quality/experiments/<id>/status`) re-derives the active tenant from the
server-side session on every call and re-checks local `Experiment` ownership
first — a tenant switch mid-poll gets a 404 on the next tick rather than
continuing to show a previous tenant's progress.

A known upstream gap (not fixable from this repo): skunkBOX's
`component_to_dict()` never returns `system_prompt`, `json_schema`,
`json_formatting_requirements`, or `release_notes`, even though `PATCH`
writes them — those fields are write-only from Cophy's UI and always render
blank on reload (documented in the Components edit form itself, and in
`docs/USER_MANUAL.md`). Similarly, there is no `model_id` enumeration
endpoint, so the Experiment-creation form takes it as a manually-typed
integer — the same established pattern as `AiAgent.skunkbox_agent_id`.

**Future work** (not yet implemented):
- Chat/attachment/knowledge-base document calls still use the older
  per-tenant credential path; migrating them onto an explicit tenant UUID
  (retiring the dual-auth-path situation above) is unscheduled future work.
- Phase 8 (cross-system audit and staged rollout) per the PRD's phased
  delivery plan.
