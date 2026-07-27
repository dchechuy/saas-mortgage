# Cross-System Operations Runbook

Cross-System Tenant AI Assets PRD, Phase 8. Covers operational procedures
spanning `saas-platform` (skunkBOX) and `saas-mortgage` (Cophy). Written
from the Cophy side; skunkBOX-specific commands assume access to that
repo's own `venv`/CLI in the same way this doc's Cophy commands assume
`.venv`.

---

## 1. Observability — current state

**What exists:**
- skunkBOX: `ServiceCredential`-authenticated management API calls are
  logged server-side via `log_management_request()` (tenant_id, operation,
  target_type, target_id, service_credential_id, outcome) — this is the
  **authoritative** audit trail for every Components/Datasets/Experiments/
  Knowledge/Agents management call, since skunkBOX is the system that
  actually executes them.
- skunkBOX: tenant-scoped `SkunkApiKey` traffic (the older customer chat/
  document API) is logged via `ApiRequestLog`.
- Cophy: the older per-tenant `Integration`/API-key path (chat, Learning
  Center document listing/detail/download) writes `ApiRequestLog` rows
  with tenant_id, integration_id, endpoint, status_code, latency_ms — see
  `app/routes/agents.py` `_log_api()`.
- Cophy: `app/skunkbox_client.py`'s `_request()` (the newer
  service-credential path — tenant lifecycle, knowledge/agent reads,
  Components/Datasets/Experiments) logs retries and network failures via
  Python's standard `logging` module, **now including the tenant UUID**
  (`log.warning("... tenant=%s: %s", tenant_id, ...)`) — added as part of
  this Phase 8 pass; previously these log lines had no tenant context.

**Known, accepted gap:** Cophy has **no local database audit-log table**
for `skunkbox_client.py` calls (unlike the older `ApiRequestLog`-backed
path). This was a deliberate choice, not an oversight: skunkBOX's own
`log_management_request()` trail is already the authoritative record of
what was actually executed for every one of these calls, and duplicating
it in Cophy would be a second, harder-to-keep-correct copy of the same
data rather than a genuinely independent check. If Cophy-side request
correlation ever becomes necessary (e.g. to debug a specific customer's
support ticket without skunkBOX access), extending `_log_api()`'s pattern
to `skunkbox_client.py`'s call sites is the natural next step — every
function there already receives the resolved tenant UUID as its first
argument, so the wiring is mechanical.

**Secret redaction:** `SKUNKBOX_SERVICE_SECRET` is read only inside
`_secret()`, placed only in the outbound `X-Service-Secret` header, and
`_request()`'s log lines only ever interpolate `exc.__class__.__name__`
(the exception type name) on failure — never the exception's full string,
never request/response bodies, never headers. Verified by
`tests/test_cross_system_tenant_sync.py::test_secret_never_appears_in_logs_on_failure`
and the "no secret in rendered HTML" tests across Phases 5–7. Apply the
same discipline to skunkBOX-side logging (`ServiceCredential` secrets are
already stored hashed there, per Phase 4, so they can't be logged even by
accident).

**Metrics:** Neither repo has a metrics/alerting stack (no Prometheus,
StatsD, or equivalent) as of this writing. The Phase 8 prompt's "Metrics
for cross-tenant denial, sync drift, API latency/error, and job failures"
requirement is met here as **log-based, manually-checked signals** rather
than dashboards/alerts:
- Cross-tenant denial: grep skunkBOX's `log_management_request()` output
  / `ApiRequestLog` for 404s on management-API routes with an
  unexpectedly high rate from one credential — a spike suggests either a
  Cophy bug or a customer probing ids.
- Sync drift: `flask sync-tenants`' exit code (`app/cli.py`) — `1` on
  fetch failure, `2` on conflicts/missing tenants, `0` clean — is
  suitable for a cron/systemd-timer wrapper to alert on non-zero.
- API latency/error: `ApiRequestLog.latency_ms`/`status_code` (both
  repos) are already captured per-call; there's no dashboard, but the raw
  data supports one being built later without a schema change.
- Job failures: skunkBOX's `experiment_runner.py` background thread — see
  that repo's own operational docs for its failure-logging behavior (out
  of scope for this Cophy-authored runbook to describe in detail).

Building real dashboards/alerting on top of this data is unscheduled
future work, not part of this phase's deliverable.

---

## 2. Runbook: partial provisioning failure

**Symptom:** A Cofficiency admin creates/edits/archives/reactivates a
tenant in Cophy; skunkBOX accepts the change, but Cophy's local mirror
write fails (network blip, DB constraint, etc.) — the flash message says
*"skunkBOX accepted this change, but the local mirror could not be
updated... Run tenant reconciliation to resolve this."*

**Response:**
1. Confirm the change actually landed in skunkBOX (skunkBOX's own
   Tenants tab under Users & Config is authoritative — check the tenant's
   name/state there).
2. In Cophy: System Config isn't the right place — use Tenant Management
   → **"Sync with skunkBOX"** (or `flask sync-tenants` from Cophy's
   `.venv`). This is idempotent — safe to run repeatedly, upserts by
   `external_id`/`public_id`, never creates a duplicate remote tenant
   (reconciliation only reads from skunkBOX, it never calls `create_tenant`
   again).
3. Confirm convergence: the tenant's row in Cophy's Tenant Management list
   should now show `sync_status=synced` and the corrected name/state.
4. If reconciliation reports a **conflict** (name/slug collision with a
   different `external_id`) instead of resolving cleanly, this needs a
   human decision — do not delete/rename either side speculatively. Follow
   §6 (Reconciliation) below.

Same procedure applies to a Component/Dataset/Experiment create that
"succeeded" per skunkBOX but whose local `Experiment` row (the one local
table Phase 7 added) failed to commit in Cophy — check skunkBOX's
Experiments admin view for the authoritative record; there is currently no
automated re-sync for `Experiment` specifically (it's a thin
UI-continuity mirror, not a reconciled table like `Tenant`) — if the local
row is missing, the customer simply won't see it in their history list
until support/engineering inserts the row manually (`skunkbox_experiment_id`,
`skunkbox_component_id`, `skunkbox_component_version_id`,
`skunkbox_dataset_id`, `skunkbox_dataset_version_id`, `created_by_user_id`
— all read straight off the skunkBOX admin view for that experiment).

---

## 3. Runbook: tenant archival

**To archive a tenant:** Cofficiency admin → Tenant Management → Archive.
This calls skunkBOX first (`skunkbox_client.archive_tenant`), then mirrors
the result locally. skunkBOX independently blocks new API activity for an
archived tenant (`403 tenant_inactive` from `require_service_credential`)
regardless of Cophy's mirror state — archival is enforced at the source of
truth, not just hidden in Cophy's UI.

**Verify:** an archived tenant's own users hitting any AI Quality page
(`/quality/components`, `/datasets`, `/experiments/new`) or attempting to
create a portal user/agent now see a clean *"This workspace has been
archived and can no longer be used"* message (added this phase —
previously this fell through to a raw skunkBOX error; see
`tests/test_cross_system_adversarial.py::test_archived_tenants_own_user_blocked_from_ai_quality_reads_and_writes`).
Existing history (conversations, Experiments list, past documents) remains
readable — archival blocks new activity, it does not erase anything.

**To reactivate:** Tenant Management → Reactivate. Same skunkBOX-first
flow in reverse.

---

## 4. Runbook: service credential rotation

The `ServiceCredential` (skunkBOX side) backing `SKUNKBOX_SERVICE_SECRET`
(Cophy side) should be rotated periodically and immediately on suspected
compromise.

1. **skunkBOX**: create a new `ServiceCredential` with the same
   capabilities as the one being replaced (`asset_management` at minimum;
   check what the current one has before assuming). Do not revoke the old
   one yet.
2. **Cophy**: update `SKUNKBOX_SERVICE_SECRET` in the deploy environment
   (never commit it — `.env` is gitignored, `.env.example` only documents
   the key name) and restart/redeploy so the new value is picked up.
   `app/skunkbox_client.py`'s `_secret()` reads it fresh from
   `current_app.config` on every call, so no code change is needed.
3. Smoke-test: as a Cofficiency admin, hit `/quality/components` (or any
   management-API-backed page) and confirm it loads without a
   `SkunkBoxClientError`.
4. **skunkBOX**: only now revoke the OLD `ServiceCredential`. Revoking
   before Cophy has successfully switched over would cause every
   management-API call to fail with `401 unauthorized` — see §5 for what
   that looks like and confirm it's *not* what you're seeing before
   declaring rotation complete.
5. Confirm the old credential's revocation doesn't affect the **old**
   per-tenant `Integration`/`X-API-Key` chat/document path at all — that's
   a completely separate credential scheme (`SkunkApiKey`, not
   `ServiceCredential`) and rotating one never touches the other.

---

## 5. Runbook: revoked/invalid service credential (incident response)

**Symptom:** every skunkBOX management-API call from Cophy starts failing.
User-visible: Components/Datasets/AI Quality pages all show *"Could not
load..."* banners; tenant sync/lifecycle actions show *"Could not
create/update/archive tenant in skunkBOX: ..."*.

**Diagnose:**
1. Check the flashed/logged error's `error_code` — `unauthorized` (401)
   means the secret itself is wrong/missing; `forbidden` (403) means the
   credential exists but lacks the required capability or was revoked;
   `tenant_inactive` (403) means the *tenant*, not the credential, is the
   problem (see §3).
2. Confirmed safe by design either way: `tests/test_cross_system_adversarial.py::test_revoked_service_credential_handled_safely_across_ai_quality_pages`
   asserts every affected page degrades to a clean error banner, never a
   500, and never falls back to showing stale data as if it were current
   (there is no local cache to fall back to in the first place — every
   page is a live proxy).
3. This is a **fail-closed** state (no functionality silently degrades
   into an insecure fallback — every check is either "call skunkBOX and
   trust its answer" or "show an error," never "guess and proceed") — the
   incident is a functionality outage for the affected feature area, not
   a data-exposure risk. `Experiment` history and past conversations
   remain visible since they don't require the credential (local rows /
   old per-tenant `Integration` path respectively).

**Resolve:** confirm current `SKUNKBOX_SERVICE_SECRET` matches an
active, non-revoked skunkBOX `ServiceCredential`; if it was intentionally
revoked, follow §4 to issue and roll out a replacement.

---

## 6. Runbook: reconciliation and mirror drift

**Manual trigger:** Cophy Tenant Management → "Sync with skunkBOX", or
`flask sync-tenants` (exit 0 clean / 1 fetch failure / 2 conflicts or
missing tenants — suitable for a cron/systemd-timer alert on non-zero).

**What it does and doesn't do** (`app/services/tenant_sync.py`):
- Upserts every tenant skunkBOX returns, matched by `external_id`/`public_id`.
- Never deletes a local tenant row; a tenant skunkBOX no longer returns is
  flagged `sync_status=error`, not removed — investigate manually (was it
  actually deleted upstream, or is this a partial/paginated response bug?).
- A name/slug collision with a *different* `external_id` is reported as a
  **conflict**, never auto-resolved — check both the local and remote
  record by hand and decide which one is correct before touching either.
- Skips the "flag missing tenants" pass entirely if skunkBOX's tenant list
  came back completely empty (treated as a probable transient/misconfigured
  response, not evidence every tenant vanished — Cofficiency itself should
  always be in a healthy response).

**Shared Agent mirror drift** (`app/services/agent_sync.py`,
`sync_shared_agents_for_tenant()`, run inline on every conversations-list
view, not on a schedule):
- A newly-shared Persona gets a local `AiAgent` mirror (`is_shared=True`)
  automatically on the next page view for each tenant — no manual action.
- An unshared/archived Persona's local mirrors are **deactivated**
  (`is_active=False`), never deleted, on the next sync for each affected
  tenant — existing conversation history keeps a valid row to point at.
  **This phase fixed a bug** where this deactivation was incorrectly
  skipped whenever a tenant's visible-shared-agent set legitimately
  dropped to zero (the guard meant for "don't trust a suspiciously-empty
  tenant list" was wrongly applied here too, where zero-visible is the
  normal starting state for most tenants) — see
  `tests/test_cross_system_adversarial.py::test_shared_agent_mirror_deactivates_when_unshared_upstream`.
- A customer's own hand-created `AiAgent` row is never touched by sync —
  ambiguous-ownership is additionally prevented at the DB level
  (`uq_ai_agent_tenant_skunkbox_agent`).

---

## 7. Runbook: unsharing a Knowledge collection or Agent

This action happens entirely on the **skunkBOX side** (Cophy has no
unshare control) — see that repo's own admin UI/docs for the
dependency-validation step (`personas.py`'s `toggle_shared_agent()`
rejects unsharing an Agent that still has private-collection
dependencies attached; `documents.py`'s collection-share toggle has the
equivalent check). From the Cophy side, after an unshare completes
upstream:
- Learning Center's collection tabs stop showing the collection (and its
  documents) for every tenant except the owning one, on the very next
  page load — no Cophy-side action needed, since Learning Center never
  caches collection state.
- Shared Agent mirrors deactivate per §6 above, per-tenant, on their next
  sync (each tenant's next conversations-list view — not instantaneous
  across all tenants simultaneously, but bounded by "next page view," not
  a scheduled job interval).

---

## 8. Runbook: general incident response checklist

1. Identify which system is affected: Cophy-only (UI/proxy bug), skunkBOX-only
   (backend/data bug), or both (credential/tenant-lifecycle issue spanning
   the boundary).
2. Check both systems' request/audit logs for the tenant UUID(s) involved
   — skunkBOX's `log_management_request()` trail and `ApiRequestLog` in
   both repos are the primary sources (see §1).
3. If cross-tenant data exposure is suspected: skunkBOX is the sole
   enforcement point for every resource this PRD covers (§16.1/§16.12 of
   the PRD) — a Cophy-side bug can, at worst, show a customer a confusing
   UI state or an unexpected 404/error, never another tenant's actual data,
   *provided* skunkBOX's own checks are intact. Confirm skunkBOX's
   response for the specific request in question (via its own logs)
   before concluding data was actually exposed versus merely mis-rendered.
4. If the credential itself is suspected compromised: rotate immediately
   per §4/§5, don't wait to fully diagnose first.
5. Document the incident and file it against whichever repo's audit doc
   (`docs/TENANT_ISOLATION_AUDIT.md` here, or skunkBOX's equivalent) needs
   an update as a result.
