# Cross-System Tenant AI Assets — Rollout Plan (Phase 8)

## Tenant Completion Phase 6 execution status — 2026-07-30

Repeatable, non-mutating rollout evidence tooling is now available:

- skunkBOX: `flask export-shared-review --output <review.md>` generates the
  authoritative collection/Agent dependency inventory. It never changes
  `is_shared`.
- Cophy: `flask tenant-rollout-preflight --environment <name> --output
  <evidence.md> --platform-inventory <review.md>` records revision,
  worktree, migration, credential-presence, tenant UUID/sync, Integration,
  feature-override, and audit baselines without printing secrets.
- Pilot/monitoring/rollback/go-no-go evidence is recorded in
  `docs/rollout/Tenant Completion Phase 6 - Pilot Record.md`.

Local-dev evidence was generated on 2026-07-30. It is explicitly **NO-GO
for deployment**: worktrees contain the implementation under review,
Cophy's service credential is not configured locally, approvals are
pending, and no pilot/observation window is named. The authoritative local
inventory contains 14 Cofficiency collections and 15 Agents; all remained
Private. No resource was automatically shared and no feature override was
changed.

Target-environment Step 1–8 checkboxes below remain intentionally open
until an operator supplies target access and stakeholders sign the review
and pilot records.

Staged rollout per `docs/prompts/Cross-System Tenant AI Assets - Prompt -
Phase 8 - saas-mortgage.md`. Each step below names the exact mechanism in
this codebase (and, where relevant, skunkBOX's) that implements it — this
is not an abstract plan, every step maps to a real flag, credential, or
command that already exists.

**Acceptance mapping**: see `docs/TENANT_ISOLATION_AUDIT.md`'s "Cross-System
Tenant AI Assets — PRD Acceptance Mapping" section for evidence against
every PRD §16/§17 criterion. **Migration/reconciliation evidence**: see
`docs/MIGRATION_REHEARSAL.md`. **Browser smoke tests**: recorded in the
Phase 6/7 CHANGELOG.md entries. This document does not repeat that
evidence — it sequences the rollout steps that consume it.

---

## Step 1 — Deploy skunkBOX schema/registry with customer management APIs disabled

skunkBOX's tenant registry, sharing columns, and Component/Dataset/
Experiment tenancy (Phases 1–3) can be deployed and migrated independently
of the customer-facing management API — the API itself is gated by
`require_service_credential()` (`app/api_auth.py`), which requires an
actual `ServiceCredential` row to exist. **Simply not creating one yet**
is the "disabled" state — no separate feature flag is needed on the
skunkBOX side for this step; the API is inert by construction until a
credential exists.

Checklist:
- [ ] skunkBOX schema migrated to head (`venv/bin/flask db upgrade`) in
  the target environment.
- [ ] Confirm no `ServiceCredential` row exists yet (or the one that does
  has no capabilities granted) — `SELECT * FROM service_credential;`
- [ ] Confirm existing skunkBOX functionality (internal admin UI, old
  per-tenant `SkunkApiKey` customer chat/document API) is unaffected —
  these are separate auth schemes from `ServiceCredential` and were not
  touched by gating the management API this way.

## Step 2 — Rehearse and validate migration

Already performed once as part of this phase — see
`docs/MIGRATION_REHEARSAL.md` for the exact commands and results
(disposable-copy upgrade, ownership audit, round-trip test, real-DB apply
with backup, for both systems). **Re-run this rehearsal against the actual
target deploy environment's data** before rollout, not just the dev
databases already verified — the commands are identical, just point
`DATABASE_URL`/the disposable copy at that environment's backup instead.

Checklist:
- [ ] Disposable-copy `flask db upgrade` succeeds cleanly in the target
  environment.
- [ ] Ownership audit query (see `docs/MIGRATION_REHEARSAL.md` §1.3) shows
  100% of pre-existing skunkBOX records Cofficiency-owned, zero on
  AdvantageFirst or any other tenant.
- [ ] Document/Collection cardinality audit shows zero multi-collection or
  zero-collection documents (or, if any exist in this environment unlike
  the dev DB, they're resolved via explicit reviewed remap before
  proceeding — never silently picked).
- [ ] Cophy UUID reconciliation (`flask sync-tenants` or the in-app "Sync
  with skunkBOX" button) converges cleanly against this environment's
  skunkBOX.
- [ ] Real-database backup taken immediately before applying (both
  systems).

## Step 3 — Configure service credential and synchronize Cophy

- [ ] Create a `ServiceCredential` on skunkBOX with capability
  `asset_management` (and `tenant_provisioning` if Cophy will also drive
  tenant lifecycle from this environment — see Phase 4's
  `MANAGEMENT_API_CONTRACT.md` for the exact capability names).
- [ ] Set `SKUNKBOX_SERVICE_SECRET` in Cophy's deploy environment to the
  generated secret; set `SKUNKBOX_BASE_URL` to this skunkBOX environment's
  URL. Never commit either value — `.env.example` in both repos documents
  the variable names only.
- [ ] Smoke-test: as a Cofficiency admin in Cophy, open Tenant Management
  and confirm the tenant list loads without a `SkunkBoxClientError`.
- [ ] Run `flask sync-tenants` (Cophy) once — confirms Cofficiency and
  AdvantageFirst's `external_id`/`public_id` UUIDs match between systems
  (see `docs/MIGRATION_REHEARSAL.md` §2.3 for what a clean result looks
  like) and `sync_status=synced` for both.
- [ ] At this point the Components/Datasets/AI Quality **feature flag is
  still off** (`ai_quality`, defaults `False` — see Step 5) and Shared
  knowledge/Agents show nothing yet (Step 4 not done) — Cophy's nav should
  show no "AI Quality" section and Learning Center should show only
  tenant-owned content, confirming the new surfaces are inert until
  deliberately enabled.

## Step 4 — Enable Shared knowledge/Agents for internal testing

This is a **skunkBOX-side, per-resource, human decision** — never
automated (PRD §10.3: "must not assume every arbitrary collection is safe
without an explicit reviewed allowlist"). As of this phase's rehearsal,
**zero** collections/Personas are marked Shared in any environment
verified so far (see `docs/MIGRATION_REHEARSAL.md` §1.3) — this step has
not been performed anywhere yet and is explicitly gated on a Cofficiency
stakeholder review, not a rollout script.

Checklist:
- [ ] Cofficiency reviews existing collections/Personas and explicitly
  marks the safe ones Shared, one at a time, via skunkBOX's admin UI
  (`documents.toggle_shared_collection` / `agents.toggle_shared_agent`).
- [ ] For each Shared Agent: confirm its dependencies (collections,
  skills/tools) are themselves either Shared or globally-safe — skunkBOX
  rejects the toggle otherwise (`toggle_shared_agent`'s dependency check).
- [ ] **Give particular attention to any Shared Agent with
  `query_experiments`/`create_dataset` MCP tools attached** — these are
  now tenant-scoped by construction (Phase 8 fix, `docs/TENANT_ISOLATION_AUDIT.md`
  finding G1 on the skunkBOX side), but this is new enough that a manual
  double-check is warranted before broad exposure: create a test
  Experiment under a non-Cofficiency test tenant, run it through a Shared
  evaluator Persona with these tools, and confirm the tool only returns
  that tenant's own experiment data (`tests/test_mcp_tenant_scoping.py`
  on skunkBOX covers this at the unit level; this is the integration-level
  re-check).
- [ ] Internal testing: as a Cofficiency admin switched into a non-Cofficiency
  test tenant in Cophy, confirm Learning Center shows the Shared collection
  labeled "Shared," and the conversation agent picker shows the Shared
  Agent labeled "Shared" — both read-only (no edit controls rendered).

## Step 5 — Enable Component/quality feature flags for Cofficiency

- [ ] In Cophy, System Config → Feature Flags → "AI Assets & Quality" →
  Edit → toggle ON, scoped to Cofficiency's own tenant only (defaults
  `False` for every tenant including Cofficiency — this is a deliberate,
  explicit per-tenant override, never a global flip for this step).
- [ ] As a Cofficiency admin with the active tenant set to Cofficiency,
  exercise the full workflow once for real: create a Component, promote a
  version, create and import a Dataset, run an Experiment, view results,
  archive/reactivate — `tests/test_ai_quality.py` covers this at the test
  level; this is the manual confirmation in the actual target environment.
- [ ] Confirm the flag is still `False`/inherited for every other tenant
  at this point (System Config → Feature Flags shows "Inherited," not
  "Overridden," for any tenant besides Cofficiency).

## Step 6 — Enable one pilot customer tenant

- [ ] Select one pilot tenant (e.g. AdvantageFirst, or a newly-provisioned
  customer tenant created via Cophy's Tenant Management, which is already
  skunkBOX-first per Phase 5).
- [ ] Toggle the `ai_quality` flag ON for that tenant specifically (same
  per-tenant override mechanism as Step 5, this time on the pilot's row).
- [ ] Confirm the pilot tenant has whatever Integrations it needs already
  configured (an "AI Agents" Integration is required for Shared Agent
  mirrors to sync at all — `app/services/agent_sync.py` skips mirroring
  entirely without one; a "Documents" Integration for Learning Center).
- [ ] Confirm the pilot tenant's `sync_status='synced'` (Tenant Management)
  — an unsynced tenant is blocked from creating portal users/agents and
  from every `/quality/*` route (Phase 5/8 checks) until reconciled.
- [ ] Have the pilot tenant's own users (not a Cofficiency admin switched
  into their workspace) exercise the workflow once, confirming they see
  only their own Components/Datasets/Experiments plus whichever Shared
  resources were enabled in Step 4, and cannot reach any other tenant's
  data by guessing an id (`tests/test_ai_quality.py::test_cross_tenant_*`,
  re-verified manually against real ids in this environment).

## Step 7 — Monitor and audit

- [ ] Watch skunkBOX's `log_management_request()` trail and both systems'
  `ApiRequestLog` tables for the pilot tenant's UUID specifically —
  elevated 404/403 rates on management-API calls from the pilot's own
  activity would indicate either a Cophy bug or a customer probing ids;
  see `docs/OPERATIONS_RUNBOOK.md` §1 for what's actually available here
  (log-based, not a dashboard, as of this phase).
- [ ] Run `flask sync-tenants` (or confirm its scheduled job, if one is
  configured) and check its exit code — non-zero means a conflict or
  missing tenant needs manual review (`docs/OPERATIONS_RUNBOOK.md` §6).
- [ ] Re-run the full test suite in both repos against the deployed
  code/schema (not just pre-deploy) as a final sanity check —
  `.venv/bin/python -m pytest -q` (Cophy, 123 tests as of this phase —
  117 Phase 5–7 plus 6 new Phase 8 adversarial tests),
  `venv/bin/python -m pytest -q` (skunkBOX, 123 passed / 2 known
  pre-existing unrelated failures in `test_evaluation.py`, see
  `docs/MIGRATION_REHEARSAL.md` §3).
- [ ] After a representative period (suggest: one full billing/reporting
  cycle, or whatever cadence the pilot engagement calls for), review the
  pilot tenant's actual usage against expectations before proceeding to
  Step 8.

## Step 8 — Expand tenant by tenant

- [ ] Repeat Step 6 for each additional tenant, one at a time — the
  per-tenant `TenantFeatureFlag` override mechanism scales to this
  naturally; there is no batch/global enablement path, which is
  deliberate (PRD: "Cofficiency can enable these incrementally per
  customer").
- [ ] Repeat the Step 6 verification checklist for each newly-enabled
  tenant — do not assume the pilot's clean result generalizes without
  re-checking sync_status/Integrations per tenant.
- [ ] Periodically revisit Step 4 as Cofficiency curates more Shared
  resources — no rollout-step re-run is needed for this, it's an ongoing
  content-curation activity independent of which tenants are enabled.

---

## Rollback / disable strategy

No step above deletes data, and every gate is a flag or credential, not a
schema/code state — rollback is symmetric with enablement:

| To roll back... | Do this | What it does NOT do |
|---|---|---|
| One pilot tenant's Components/Datasets/AI Quality access | Reset the `ai_quality` `TenantFeatureFlag` override for that tenant to inherited (or explicitly override to `False`) | Does not delete any Component/Dataset/Experiment data on skunkBOX — it becomes unreachable through Cophy's UI for that tenant, nothing is destroyed. Re-enabling later picks up exactly where it left off. |
| Every tenant's Components/Datasets/AI Quality access at once | Flip the global `FeatureFlag.is_enabled` for `ai_quality` to `False` (System Config, admin-only) | Individual tenant overrides still apply on top of this — a tenant explicitly overridden to `True` would still see it; clear per-tenant overrides first if a true global lockout is needed. |
| A specific Shared knowledge collection or Agent | Unshare it on skunkBOX (`toggle_shared_collection`/`toggle_shared_agent`) — validates no other Shared resource still depends on it first | Local Cophy `AiAgent` mirrors for that Agent are deactivated (not deleted) on their next sync (`docs/OPERATIONS_RUNBOOK.md` §6) — existing conversation history remains intact and readable. |
| The entire cross-system integration (emergency) | Revoke the `ServiceCredential` on skunkBOX (`docs/OPERATIONS_RUNBOOK.md` §4/§5) | Every `skunkbox_client.py` call in Cophy starts failing closed with a clean error banner (verified: `tests/test_cross_system_adversarial.py::test_revoked_service_credential_handled_safely_across_ai_quality_pages`) — no data loss, no insecure fallback, existing local `Experiment` history and past conversations remain visible since they don't require the credential. |
| A specific tenant entirely | Archive the tenant on skunkBOX (Cophy mirrors it) — blocks new API activity without erasing history (`docs/OPERATIONS_RUNBOOK.md` §3) | Existing data remains queryable by Cofficiency admins; the tenant's own users are blocked from all new activity with a clean message (Phase 8 fix — previously fell through to a raw skunkBOX error). |

In every case: **archive/disable/revoke, never delete**, matching every
lifecycle operation built across Phases 1–7 (no hard-delete exists
anywhere in the customer-facing surface of either system —
`docs/TENANT_ISOLATION_AUDIT.md` confirms this structurally for both
repos).
