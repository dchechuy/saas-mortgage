# Phase 5 — Cophy Authoritative Tenant Synchronization

You are working on `saas-mortgage` (Cophy Portal).

Read:

- `docs/prompts/Cross-System Tenant AI Assets - PRD.md`
- Completed skunkBOX Phases 1–4 and their tenant API contract
- Existing Cophy tenant implementation, audit, tests, and architecture
- Any repository agent instructions

Implement only Phase 5.

---

## Goal

Preserve Cophy's local tenant isolation while making skunkBOX authoritative for tenant lifecycle and synchronizing by stable UUID.

---

## Schema and migration

Add immutable, unique, non-null `Tenant.external_id` containing skunkBOX `Tenant.public_id`.

Migration/setup:

- Obtain or configure authoritative Cofficiency and AdvantageFirst UUIDs.
- Map existing local Cofficiency and AdvantageFirst rows without changing local IDs or ownership.
- Never generate conflicting cross-system UUIDs independently in production.
- Provide a controlled bootstrap path for development/test databases.
- Add synchronization status/timestamps if useful, but avoid treating stale status as authorization to bypass skunkBOX.

All existing Cophy users/assets/logs remain in their already implemented local tenants.

---

## skunkBOX service client

Create a focused client module:

- Base URL and service credential from environment/config
- Tenant lifecycle calls
- Full/updated-since tenant listing
- Timeouts, consistent errors, retries only when safe
- Idempotency keys for create
- No secret logging
- Test doubles/fixtures

Do not scatter raw HTTP calls across routes.

---

## Tenant lifecycle UI

Keep the existing Cofficiency-admin tenant screen, but:

- List from the local mirror with clear sync state.
- Create calls skunkBOX first and then upserts local mirror by UUID.
- Edit/archive/reactivate calls skunkBOX first and applies returned state locally.
- Do not permit a local-only lifecycle mutation.
- Preserve protected Cofficiency rules.
- On partial failure after authoritative success, show a recoverable error and allow reconciliation.
- Prevent creation of portal users/assets under an inactive or unsynchronized tenant.

The authoritative skunkBOX Tenants tab remains the source of truth; Cophy is a convenient proxy/mirror.

---

## Reconciliation

Add Cofficiency-admin manual sync and a CLI command suitable for scheduled execution:

- Fetch authoritative tenant list.
- Upsert by `external_id`.
- Update name/slug/active state.
- Detect, report, and refuse ambiguous duplicate UUID/name/slug mappings.
- Never delete local tenant rows.
- Never rewrite `User.tenant_id` or historical ownership.
- If an active tenant becomes archived, existing active-tenant fallback continues to Cofficiency.

Log reconciliation results without secrets.

---

## Trusted tenant propagation

Extend Cophy's skunkBOX client foundation so future calls supply active tenant `external_id` using the Phase 4 contract and service credential.

- Resolve UUID from server-side active tenant.
- Never accept browser-supplied tenant context.
- Existing tenant-specific Integration/API-key behavior remains defense in depth.
- A missing UUID blocks the cross-system operation safely.

Do not build customer asset UI yet.

---

## Tests

Cover:

- UUID mapping migration
- Local ownership unchanged
- Create/edit/archive/reactivate authoritative-first behavior
- Idempotent retry after partial failure
- Full reconciliation
- Duplicate/drift detection
- No local deletion/reassignment
- Archived active-tenant fallback
- External users cannot administer/sync tenants
- Active UUID derives server-side
- Service secrets never reach HTML/logs

Run the full suite.

---

## Deliverables

- External UUID schema/migration
- skunkBOX service client
- API-backed tenant lifecycle UI
- Reconciliation command/action
- Trusted tenant propagation foundation
- Tests/documentation

