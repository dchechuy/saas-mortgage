# Architecture

## Overview

`saas-mortgage` is a monolithic Flask application designed as a reusable foundation for future SaaS prototypes.

## Core stack

- Frontend: HTML, Jinja templates, lightweight CSS
- Backend: Python Flask
- Database: SQLite via SQLAlchemy
- Auth: Flask-Login
- Migrations: Flask-Migrate

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

### skunkBOX interim boundary

skunkBOX (the external AI/document backend) does not yet accept a tenant ID.
Isolation is indirect: each tenant has its own `Integration` credentials, and
`AiAgent`s reference only same-tenant integrations. Every chat, attachment,
and Learning Center/knowledge-base call resolves its integration through the
active tenant (or the owning conversation's tenant) before making the
outbound request — a cross-tenant integration/agent reference is rejected
locally first. No speculative tenant field is sent to skunkBOX.

**Future work** (not yet implemented):
- Calls must be tenant-owned when that feature is built.
- Components / AI Assets require a tenant-aware skunkBOX management API,
  which doesn't exist yet.
- skunkBOX requests will eventually carry an explicit tenant ID in addition
  to today's tenant-specific credentials.

