# Tenant Isolation Audit

Repository-wide audit performed at the end of Phase 6 of Tenant Separation
(see `docs/prompts/Tenant Separation - PRD.md` and the six phase prompts
under `docs/prompts/`). Method: grepped every `.query`, `filter_by`,
`db.session.get`, `db.get_or_404`, bulk `.update()`/`.delete()`, and raw-SQL
call site in `app/` against each tenant-owned model, then verified each site
against the checklist below. No global SQLAlchemy tenant filter was
introduced — every predicate is explicit, matching the repository's existing
style of route-level checks over model-level magic.

For each tenant-owned model:
1. List queries filter active tenant.
2. Creates assign tenant server-side.
3. Direct reads/mutations validate tenant.
4. Related records belong to the same tenant.
5. Bulk operations include tenant.
6. Dropdown/filter data is tenant-limited.
7. Aggregates and exports are tenant-limited.

---

## Tenant-owned models — status: all criteria satisfied

### `User`
- List/counts: `app/routes/users.py` (`list_users`), `app/routes/main.py` and `app/routes/reporting.py` dashboards, `app/routes/agents.py` (conversation user filter), `app/routes/reporting.py` (activity user filter) — all filter by `tenant_id=active_tenant_id`.
- Create: `add_user` assigns `tenant_id` from the server-resolved active tenant only; the field is never read from the request.
- Direct reads/mutations: `edit_user`, `toggle_user`, admin `upload_avatar` call `require_tenant_record(user)` immediately after fetch (404 on mismatch), before any data is read or form fields processed.
- Related records: n/a (no FK from another tenant-owned model targets a specific user beyond actor attribution, which is intentionally global — see below).
- Bulk: none exist for `User`.
- Dropdowns: agent/user conversation filters and the activity-log user filter are tenant-limited.
- Intentionally NOT tenant-filtered: the Flask-Login `user_loader` (`app/__init__.py`) and the login lookup (`app/routes/auth.py`) — both are global identity lookups that must find a user *before* any tenant context exists. Username/email uniqueness checks in `add_user`/`edit_user` are deliberately global (login identity is global per the PRD). `_seed_defaults()`'s admin-existence check is startup seeding, not a tenant surface.

### `LlmModel`
- List: `models.py` System Config tab, dashboards, reporting filter dropdown — all `tenant_id`-scoped.
- Create: `add_llm_model` assigns tenant from active tenant; duplicate-name check is tenant-scoped; "clear other defaults" bulk update is tenant-scoped (`LlmModel.query.filter_by(tenant_id=...).update(...)`), so setting one tenant's default never touches another's.
- Direct reads/mutations: `update_llm_model`, `toggle_llm_model` call `require_tenant_record(model)`.
- Related: n/a.
- Bulk: the default-clearing update above is the only bulk op; tenant-scoped.
- Dropdowns/selection outside `routes/models.py`: `doc_generator.py._get_model()`, `release_manager.py`'s model selection, and `help.py`'s `improve_doc_prompt` model lookup all resolve via `get_active_tenant_id()` rather than a bare "first active model" query.
- Aggregates: Reporting's LLM tab (see below).

### `Attribute`
- List: System Config tab, dashboards — tenant-scoped.
- Create: `batch_save_attributes` requires an active, *active-status* tenant before any write; new rows get `tenant_id` from it.
- Direct reads/mutations: the batch route checks `attr.tenant_id == active_tenant.id` per row for both edits and deletes (not just category match) before touching it.
- Bulk: the batch save/delete loop is the bulk surface; every row-level check includes tenant.
- Dropdowns: n/a (attributes aren't used as a foreign-key selector elsewhere).

### `Integration`
- List: System Config tab, agent-creation integration picker, dashboards, reporting filter dropdown, `_get_docs_integration()` (Learning Center) — all tenant-scoped.
- Create: `add_integration` assigns tenant from active tenant; duplicate-name check is tenant-scoped.
- Direct reads/mutations: `save_integration` calls `require_tenant_record(integration)`.
- Related: `AiAgent.integration_id` is validated to belong to the *same* tenant as the agent on both create and update (`add_agent`, `save_agent`) — a cross-tenant integration reference is rejected with a flashed error, not silently accepted.
- Secrets: encrypted API keys are never decrypted for display in any template; combined with tenant-scoped listing, another tenant's integration metadata (or the presence of a key) is never rendered.

### `AiAgent`
- List: System Config tab, conversation "start new" picker (`list_conversations`) — tenant-scoped.
- Create: `add_agent` assigns tenant from active tenant and validates the chosen integration belongs to it.
- Direct reads/mutations: `save_agent`, `toggle_agent`, and `new_conversation`'s agent lookup all call `require_tenant_record(agent)`.
- Related: agent→integration tenant match enforced at write time (see `Integration` above); conversation→agent tenant match enforced at conversation-creation time (see `AgentConversation` below).
- Bulk: `toggle_agent`'s "archive this agent's conversations" update includes both `ai_agent_id` and `tenant_id` predicates (the latter is logically redundant given a global agent id, but kept as defense-in-depth per the Phase 4 instruction to include tenant in every predicate).
- Avatar storage: filenames are randomly generated (`uuid4().hex`), not derived from any guessable tenant/agent identifier, so storage naming cannot be used for cross-tenant access.

### `AgentConversation`
- List: `list_conversations`' base query (all of Mine/All/Favorites), the empty-conversation auto-cleanup, and the last-used-agent calculation all filter `tenant_id == active_tenant_id`.
- Create: `new_conversation` sets `tenant_id=agent.tenant_id` (equal to the active tenant, since the agent was already validated) — this was a genuine pre-existing bug (the column was never set at all before Phase 5) and is now fixed and covered by a regression test.
- Direct reads/mutations: `view_conversation`, `archive_conversation` (`require_tenant_record`); `send_message`, `upload_attachment`, `toggle_favorite` (inline `conv.tenant_id != get_active_tenant_id()` → JSON 404, matching each route's existing JSON error contract instead of an HTML abort).
- Related: message/attachment ownership is established by joining through the owning conversation and checking *that* conversation's tenant (`download_attachment`), not just the actor's identity — closing the "switch tenant, reuse an old URL" gap.
- Bulk: the auto-cleanup delete and the agent-deactivation archive update both include a tenant predicate.
- Filters: agent/user/date filters in `list_conversations` operate only within the already tenant-filtered base query.

### `LlmRequestLog`, `UserActivityLog`, `ApiRequestLog`
- Every constructor site (`activity_logger.log_activity`, the `_log()` closures in `release_manager.py`/`doc_generator.py`, `agents.py`'s `_log_api`) resolves a non-null tenant ID before writing, and **skips the write entirely** (never inserts a null tenant_id) if none can be resolved — which in practice only happens for anonymous/unauthenticated actions.
- `ApiRequestLog.tenant_id` is attributed to the called integration's own owning tenant (not a re-resolved "current active tenant"), so the log stays tied to the resource actually invoked.
- `UserActivityLog` is attributed to the actor's *resolved active* tenant, never their home tenant — a Cofficiency actor working in a customer tenant produces activity for that customer tenant.
- Reporting (`app/routes/reporting.py`) filters all three log tables' base queries, derived aggregates (totals, error rates, average latency, total tokens, active-user counts, top action), filter-dropdown data, and pagination from a single tenant-and-date-filtered query object per tab — aggregates are never calculated globally while the list is tenant-filtered.
- The Activity tab filters by `UserActivityLog.tenant_id`, not `User.tenant_id`, per the Phase 6 requirement (the actor may be Cofficiency while the event belongs to a customer tenant).
- The API tab filters by the log row's own stored `tenant_id`, not the integration's current tenant, so a later reconfiguration can't rewrite history.
- Logging failures are still swallowed in production (fail-safe — a broken log write must never break the user's request), but now re-raise under `current_app.testing` (`activity_logger.reraise_if_testing()`) so a schema/programming bug in a log-writing path fails loudly in tests instead of silently vanishing as "no log row was written."

### `TenantFeatureFlag`
- The global `FeatureFlag` catalogue/default is untouched by tenant actions. `TenantFeatureFlag` rows are looked up, created, updated, and deleted only by `(tenant_id=active_tenant.id, feature_flag_id=flag.id)` in `models.py`'s `toggle_flag`/`reset_flag`, and by the shared resolver in `app/feature_flags.py` (`effective_feature_flags`/`is_feature_enabled`), which every template/nav/route check goes through.
- Route-level enforcement: `access.feature_required(key)` blocks the underlying route (not just the nav link) when a flag is disabled for the active tenant — verified for `conversations`, `learning_center`, and `system_overview`.

---

## Intentionally global (verified, not gaps)

| Surface | Why |
|---|---|
| `Role` / `Permission` | Global reusable permission templates (PRD §7.3). Renaming/deleting a role in `permissions.py` intentionally affects users in every tenant who hold that role name. |
| `ReleaseNote` | Shared product history, same content regardless of active tenant. |
| `NavSection` / `NavItem` | Global application structure; the PRD explicitly keeps these editable by any admin with existing `attributes:edit` permission (not Cofficiency-gated) — a deliberate v1 scope decision, not an oversight. |
| `DocPrompt` | Global documentation-generation configuration. |
| `FeatureFlag` (the catalogue rows themselves) | Global default state; only the per-tenant override table is tenant-owned. |
| User Documentation (`help.py` quick-start/user-manual/architecture) and Release Notes | Explicitly global per the PRD; verified their routes only ever query the global models above. |
| `Tenant` row access in `app/routes/tenants.py` | Tenant management is inherently cross-tenant for a Cofficiency admin (that's the feature) — gated by `cofficiency_admin_required`, not a per-record tenant match. |
| `_seed_defaults()` admin/attribute existence checks | Startup seeding logic, not a request-time tenant surface; already hardcodes Cofficiency/AdvantageFirst per the Phase 1 migration semantics. |

## Explicitly deferred (out of scope per the PRD)

- **Calls**: feature does not exist yet; PRD requires it be tenant-owned when built.

The two items formerly listed here — "Components / AI Assets" and "the
skunkBOX tenant-ID contract" — are no longer deferred. Both were built by
the separate, later **Cross-System Tenant AI Assets PRD** (Phases 5–7 on
this repo's side); see the dedicated audit section below, added for that
PRD's own Phase 8 ("cross-system audit and rollout").

## No global query hook

Per the PRD ("Avoid relying on SQLAlchemy global query hooks... explicit service helpers and query predicates are easier to audit"), every tenant filter above is an explicit predicate or a call to a small shared helper (`tenant_context.get_active_tenant_id()`, `tenant_context.require_tenant_record()`, `feature_flags.effective_feature_flags()`). No `before_compile` / global `Query` override was introduced.

---

# PRD Acceptance Criteria Mapping (Phase 6 final checklist)

Maps every criterion in `docs/prompts/Tenant Separation - PRD.md` §16–17 to
its implementation and test evidence. All 69 tests pass as of this writing
(`.venv/bin/python -m pytest tests/` → `69 passed`).

## §16 — Security Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | External user cannot change active tenant via request data, cookies, sessions, or URLs | ✅ | `tenant_context._resolve_active_tenant()` never reads the request for external users — it always returns `user.tenant`, full stop. `tests/test_tenant_phase2.py::test_external_user_cannot_switch_even_forged`, `tests/test_tenant_adversarial.py::test_external_user_cannot_switch_by_any_means` (forged POST body and an unrelated query parameter) |
| 2 | External user cannot list/read/edit/toggle/archive/reference another tenant's records | ✅ | `require_tenant_record()` + inline tenant checks on every direct-ID route (see audit above). `tests/test_tenant_phase3.py::test_cross_tenant_edit_toggle_avatar_rejected`, `tests/test_tenant_phase5.py::test_cross_tenant_direct_operations_rejected`, `tests/test_tenant_adversarial.py::test_cross_tenant_ids_fail_for_every_route` |
| 3 | Cofficiency user cannot access a selected tenant's page without existing required role permission | ✅ | Tenant resolution is additive to `permission_required`/`feature_required`, never a bypass — switching changes *what* data a permitted page shows, not *whether* the page is reachable. `tests/test_tenant_phase2.py::test_permissions_still_apply_after_switching`, `tests/test_tenant_adversarial.py::test_limited_cofficiency_user_retains_limitations_after_switching` |
| 4 | Forged agent/integration/model/user/conversation ID from another tenant is rejected | ✅ | Covered per-model in the audit above. `tests/test_tenant_phase4.py::test_agent_cannot_reference_another_tenants_integration`, `test_cross_tenant_update_toggle_batch_rejected`; `tests/test_tenant_phase5.py::test_forged_cross_tenant_agent_id_rejected`; `tests/test_tenant_adversarial.py::test_cross_tenant_agent_integration_reference_fails` |
| 5 | Tenant switching accepts only active tenants; CSRF-protected per project conventions | ✅ | `switch_tenant()` validates `Tenant.query.filter_by(id=target_id, is_active=True)` — an inactive or nonexistent target is rejected (`tests/test_tenant_phase2.py::test_cofficiency_user_default_resolution`, `test_tenant_adversarial.py::test_inactive_tenants_cannot_be_selected_or_receive_data`). Repository-wide Flask-WTF protection now rejects missing/invalid switch tokens before route code runs; `tests/test_csrf_protection.py::test_tenant_switch_rejects_missing_and_invalid_token_and_reuses_valid_token` also proves a valid session token remains usable across ordinary workspace switches. |
| 6 | User tenant assignment cannot be mutated through UI or crafted requests | ✅ | No route reads or writes `User.tenant_id` after creation; `add_user`/`edit_user` never accept a `tenant_id` form field even when one is forged into the POST body. `tests/test_tenant_phase3.py::test_add_user_gets_active_tenant_and_ignores_forged_tenant_id`, `test_existing_user_tenant_cannot_be_changed_via_edit`; `tests/test_tenant_adversarial.py::test_tenant_assignment_immutable_via_crafted_forms` |
| 7 | Bulk operations cannot affect another tenant | ✅ | Every bulk `.update()`/`.delete()` site carries a tenant predicate (see audit above). `tests/test_tenant_phase4.py::test_cross_tenant_update_toggle_batch_rejected`; `tests/test_tenant_adversarial.py::test_bulk_operations_cannot_affect_another_tenant` |
| 8 | Reporting never mixes tenant-owned rows | ✅ | All three Reporting tabs' base queries, aggregates, and filter dropdowns share one tenant-and-date-filtered query object per tab (Phase 6). `tests/test_tenant_adversarial.py::test_reports_and_aggregates_contain_only_event_tenant` |
| 9 | Feature flags cannot leak state or navigation across tenants | ✅ | `TenantFeatureFlag` rows and `effective_feature_flags()` are always tenant-keyed; nav visibility and route access (`feature_required`) use the same resolver. `tests/test_tenant_phase4.py::test_tenant_override_changes_only_selected_tenant`, `test_navigation_and_route_use_same_effective_flag_state`; `tests/test_tenant_adversarial.py::test_feature_override_does_not_affect_another_tenant` |
| 10 | Global documentation and release notes remain available without exposing tenant data | ✅ | `help.py`'s doc/release-note routes only ever query global `ReleaseNote`/`DocPrompt` models — verified no tenant-owned query was introduced there. `tests/test_tenant_phase5.py::test_docs_and_release_notes_visible_across_tenant_switches`; `tests/test_tenant_adversarial.py::test_global_surfaces_remain_global`; manual check against the real pre-tenant DB backup (release notes and quick-start both returned 200 across three tenant switches) |

## §17 — Functional Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Cofficiency and AdvantageFirst created during migration | ✅ | `migrations/versions/7f7733a2f7d0_...`; `tests/test_tenant_migration.py::test_exactly_one_cofficiency_and_one_advantagefirst_tenant`; verified on the real pre-tenant DB backup at final acceptance |
| 2 | Existing admin signs in as Cofficiency user, initially operates in AdvantageFirst | ✅ | Migration sets `admin.tenant_id=cofficiency`, `admin.last_active_tenant_id=advantagefirst`. `tests/test_tenant_migration.py::test_existing_admin_home_tenant_is_cofficiency`, `test_existing_admin_remembered_tenant_is_advantagefirst` |
| 3 | Existing external users and business data continue working under AdvantageFirst | ✅ | All pre-existing users/models/attributes/integrations/agents/conversations backfilled to AdvantageFirst with row counts preserved. `tests/test_tenant_migration.py::test_existing_non_admin_users_are_advantagefirst`, `test_existing_tenant_owned_records_are_advantagefirst`; real-backup migration re-verified counts identical pre/post |
| 4 | Cofficiency users see a tenant switcher left of the avatar | ✅ | `app/templates/base.html` renders the switcher immediately before the avatar button, gated on `can_switch_tenants`. `tests/test_tenant_phase2.py::test_header_switcher_visibility_and_label`; visually confirmed in-browser during Phase 2 |
| 5 | External users do not see the switcher | ✅ | Same gate as above, `can_switch_tenants` is `is_cofficiency_user`-only. `tests/test_tenant_phase2.py::test_header_switcher_visibility_and_label`; `tests/test_tenant_adversarial.py` (jane/bob never switch successfully) |
| 6 | Cofficiency user's most recent tenant persists across logout/login and browser sessions | ✅ | Persisted in `User.last_active_tenant_id` (database-backed, not session-only). `tests/test_tenant_phase2.py::test_switch_persists_across_new_login` |
| 7 | Cofficiency-selected-as-active shows Cofficiency users only, no AdvantageFirst operational assets | ✅ | `tests/test_tenant_phase3.py::test_user_list_and_counts_are_tenant_isolated` |
| 8 | Creating a user assigns active tenant, no selectable tenant field | ✅ | `add_user` template has no tenant input; route assigns from `get_active_tenant()`. `tests/test_tenant_phase3.py::test_add_user_gets_active_tenant_and_ignores_forged_tenant_id` |
| 9 | Tenant assignment remains immutable | ✅ | See §16.6 above. |
| 10 | Models/attributes/integrations/agents/conversations/knowledge-base/dashboards/feature flags/reporting follow active tenant | ✅ | Phases 4–6; see the per-model sections of this audit above |
| 11 | Historical reports appear under AdvantageFirst | ✅ | Migration backfill + `tests/test_tenant_adversarial.py::test_historical_seeded_logs_remain_advantagefirst` |
| 12 | New Cofficiency-user actions appear in the selected tenant's report | ✅ | `log_activity()` resolves the actor's active tenant, not home tenant. `tests/test_tenant_phase3.py::test_activity_uses_active_tenant_while_actor_stays_cofficiency`; `tests/test_tenant_adversarial.py::test_cofficiency_actor_activity_appears_in_selected_tenant` |
| 13 | User Documentation and Release Notes unchanged across tenant switches | ✅ | See §16.10 above. |

## Resolved cross-cutting gap: CSRF

The repository-wide CSRF gap identified by the original tenant-separation
audit is closed. Flask-WTF protection is initialized centrally, every
server-rendered mutation form carries a token, and same-origin AJAX/JSON
mutations send the token in `X-CSRFToken`. This includes login/logout and
password changes, tenant lifecycle and switching, user/avatar management,
roles, feature flags and configuration, conversations, AI Quality proxy
operations, uploads, and documentation/release administration.

There are no Client Portal CSRF exemptions: no inbound mutation endpoint
uses a machine-to-machine authentication scheme. Safe failure handling and
the tenant-specific regression evidence are in
`tests/test_csrf_protection.py`. CSRF remains only one layer; the tests also
confirm that a valid token does not bypass active-tenant ownership checks.

---

# Cross-System Tenant AI Assets — Cophy-side Ownership Audit (Phase 8)

Separate PRD from Tenant Separation above (`docs/prompts/Cross-System
Tenant AI Assets - PRD.md`, Phases 1–7 completed on the saas-platform side
and Phases 5–7 on this repo). Covers everything added since the audit
above was written: skunkBOX becoming the authoritative tenant registry,
Shared knowledge/Agent read access, and Components/Datasets/AI Quality
management. See `saas-platform/docs/TENANT_ISOLATION_AUDIT.md` (produced
alongside this one, as part of this same Phase 8 pass) for the skunkBOX-side
classification of the same PRD's models and its own findings — most
notably **G1**: `mcp_server/server.py`'s `query_experiments`/`create_dataset`
MCP tools had no tenant filter at all, a real cross-tenant data-disclosure
path reachable through a Shared evaluator/summary Persona used by any
tenant's Experiment. Fixed and tested on the skunkBOX side this phase
(`tests/test_mcp_tenant_scoping.py`) — flagged here because it directly
affects this repo's own "Shared Agents are read/use only" guarantee: a
Shared Agent with `query_experiments`/`create_dataset` attached could
previously have returned another tenant's data through a conversation
started from Cophy, even though Cophy's own tenant-scoping was correct
end-to-end. No Cophy-side code change was needed — the fix is entirely in
how skunkBOX threads tenant context into its own background/MCP tool
execution.

## Model classification (Cophy side)

| Model | Bucket | Reason |
|---|---|---|
| `Tenant` | Local mirror of an authoritative record | No longer authoritative (PRD §6.2) — `external_id` maps to skunkBOX `Tenant.public_id`; `sync_status`/`last_synced_at` track mirror freshness. Local `id` and FK relationships (`User.tenant_id`, etc.) are unaffected — this repo's own tenant isolation still keys off the local integer id, same as the Tenant Separation audit above. |
| `AiAgent` | Mixed: tenant-owned (`is_shared=False`) + system-managed mirror of Cofficiency-owned-Shared (`is_shared=True`) | A `is_shared=True` row is a **local, per-tenant pointer** to a skunkBOX Shared Persona, not itself shared/joint-owned — its `tenant_id` is always the customer using it, never Cofficiency's. See `app/services/agent_sync.py`. |
| `Experiment` | Tenant-owned, minimal mirror | Required `tenant_id`; exists solely for UI continuity (skunkBOX has no experiment-list endpoint) — see `app/models.py`'s `Experiment` docstring. Never shared. |
| Components / Datasets (skunkBOX-side) | Not mirrored at all | Cophy holds zero local rows for these — every read/write proxies live through `app/skunkbox_client.py` with the active tenant's UUID; skunkBOX is the sole source of truth and sole enforcement point. |
| Knowledge collections / documents (skunkBOX-side) | Not mirrored at all | Same as above — `app/routes/agents.py` Learning Center routes are a stateless proxy (old per-tenant `Integration`/API-key path for content, new management-API path for the collection list/labels); no local `Document`/`DocumentCollection` table exists in this repo. |
| `Integration` (`use_case="AI Agents"` rows used by Shared mirrors) | Tenant-owned (pre-existing) | Unchanged by this PRD — a Shared Agent mirror still authenticates through the *customer's own* Integration row, never a Cofficiency credential, so no new sharing semantics were introduced to this model. |

## New/changed surfaces, request-reachable

### `app/skunkbox_client.py` (the service-credential HTTP client)
Every function takes a `tenant_id` (the skunkBOX UUID) as an explicit,
mandatory parameter — there is no "current tenant" global state or
implicit fallback inside this module. Every call site resolves that
argument via `tenant_context.require_active_tenant_external_id()` /
`get_active_tenant_external_id()`, which read only the server-resolved
active tenant (`tenant_context.get_active_tenant()`) — never a request
header, form field, session value, or query string. Verified by grep: no
call site in `app/routes/quality.py`, `app/routes/tenants.py`, or
`app/services/agent_sync.py` passes anything from `request.*` as the
`tenant_id` argument. `tests/test_cross_system_tenant_sync.py::test_get_active_tenant_external_id_ignores_request_data`
proves this directly by injecting a forged `X-Tenant-Id` header and query
param and confirming the resolved UUID is unaffected.

Cross-tenant/forged resource ids (component id, dataset id, experiment id,
collection id, agent id) are never independently re-validated by Cophy —
they're passed straight through with the correct tenant UUID, and skunkBOX
itself 404s a mismatch. This is a deliberate "thin proxy, single
enforcement point" design (matching the "Cophy calls only documented
skunkBOX domain APIs... does not recreate ... state machines locally"
instruction), not a gap — the alternative (Cophy maintaining its own
shadow ownership table for records it doesn't otherwise store) would be a
second, harder-to-keep-correct enforcement point. `Experiment` is the one
exception with a real local row, and it uses the standard
`require_tenant_record()` pattern (see below).

### `app/routes/quality.py` (Components / Datasets / Experiments)
- Every route resolves the active tenant's UUID via `_tenant_ext_id_or_flash()`
  → `require_active_tenant_external_id()`; a missing/unsynced tenant fails
  closed (flash + no skunkBOX call), never falls back to a guessed value.
- `view_component`/`save_component`/`promote_component`/`archive_component`/
  `reactivate_component`, and the Dataset equivalents, all catch a `404`
  `SkunkBoxClientError` and `abort(404)` locally — a cross-tenant/forged id
  produces the same 404 a customer would see for a typo'd id, no
  existence disclosure.
- `view_experiment`/`experiment_status` are the one place with a **local**
  ownership check: `require_tenant_record(experiment)` (view) and an
  inline `experiment.tenant_id != get_active_tenant_id()` check (status
  poll, since it returns JSON not an abort) — both run *before* any
  skunkBOX call, so a cross-tenant local experiment id never even reaches
  the client with the wrong tenant UUID. Covered by
  `tests/test_ai_quality.py::test_cross_tenant_experiment_id_404s`,
  `test_switching_active_tenant_invalidates_open_experiment_poll`.
- `new_experiment`'s picker (`GET`) only ever lists the active tenant's own
  Components/Datasets (via `skunkbox_client.list_components`/`list_datasets`,
  both tenant-scoped server-side) — there is no cross-tenant option to even
  select by mistake. `tests/test_ai_quality.py::test_experiment_picker_only_offers_same_tenant_resources`.
- Dataset CSV import: file is read and parsed entirely server-side; the
  parsed `rows` are sent to skunkBOX over the existing tenant-scoped
  `import_dataset_rows()` call — no separate tenant check needed since the
  target `dataset_id` already goes through the same 404-on-mismatch path
  as every other Dataset route.
- No hard-delete, optimizer, or internal-audit route exists anywhere in
  this blueprint — archive/reactivate (soft state) is the only lifecycle
  mutation, matching what skunkBOX's management API itself exposes.
  `tests/test_ai_quality.py::test_no_delete_or_optimizer_routes_exist_under_quality`
  asserts this structurally (no `DELETE` method, no `optimizer`/`delete`
  substring in any `/quality/*` rule).

### `app/services/agent_sync.py` (Shared Agent mirroring)
- `sync_shared_agents_for_tenant(tenant)` only ever upserts local `AiAgent`
  rows scoped to the **tenant passed in** — it is called once per request
  with the current request's own active tenant (`app/routes/agents.py`
  `list_conversations()`), never in a loop over "all tenants," so there is
  no code path where one tenant's sync could write a row under another's
  `tenant_id`.
- Ambiguous-ownership guard: `(tenant_id, skunkbox_agent_id)` is a DB-level
  unique constraint (`uq_ai_agent_tenant_skunkbox_agent`,
  `migrations/versions/k1l2m3n4o5p6_add_ai_agent_is_shared.py`) — even a
  future code bug attempting to create a second local row for a
  `skunkbox_agent_id` a tenant already has mirrored/owns raises an
  `IntegrityError` rather than silently succeeding; the service layer
  catches this per-row and reports a conflict instead of crashing the
  whole sync.
- A Shared mirror's underlying chat calls still authenticate with the
  *customer's own* `Integration` row (never a Cofficiency credential) —
  confirmed by construction: `sync_shared_agents_for_tenant()` requires
  `Integration.query.filter_by(tenant_id=tenant.id, use_case="AI Agents", ...)`
  and skips creating any mirror at all if the tenant has none.
- `app/routes/models.py` `save_agent`/`toggle_agent` reject any mutation of
  an `is_shared=True` row before touching the database — a customer cannot
  repoint or deactivate a Shared mirror to affect other tenants' view of
  the same underlying skunkBOX Agent (there's nothing shared to affect;
  each tenant has its own independent mirror row, but the guard exists so
  a customer can't be misled into thinking they're editing "their" copy of
  a Cofficiency-managed Agent).

### `app/services/tenant_sync.py` (tenant lifecycle reconciliation — Phase 5, re-confirmed for Phase 8)
- `run_reconciliation()` never deletes a local `Tenant` row and never
  rewrites `User.tenant_id` — a tenant no longer returned by skunkBOX is
  flagged `sync_status='error'`, not removed, so no FK referencing it ever
  dangles and no user's home-tenant assignment can be silently reassigned
  by a sync run.
- Name/slug collision with a *different* `external_id` raises
  `TenantSyncError` and is reported as a conflict rather than guessed —
  never silently renames/reslugs over an existing local tenant.
- Skips the "flag tenants missing from skunkBOX" pass entirely when the
  remote response was empty (`if remote_tenants else []` in
  `run_reconciliation`), so a transient/misconfigured empty API response
  can't be misread as "every tenant was deleted upstream" and mass-flag
  every local tenant `sync_status='error'`.

## Bulk operations / raw SQL / background surfaces
- No raw SQL (`db.session.execute(text(...))`) touches any tenant-owned
  table introduced by this PRD — every Components/Datasets/Experiments
  read/write goes through the ORM `Experiment` model or the
  `skunkbox_client` HTTP layer, neither of which has a raw-SQL path.
- No background worker/job exists on the Cophy side for this PRD —
  `sync_shared_agents_for_tenant()` and Learning Center's document fetch
  are both synchronous, in-request calls (same "always live, no scheduled
  job" pattern as pre-existing Learning Center), so there is no
  stale-tenant-context risk from a job outliving the request that enqueued
  it. (skunkBOX's own Experiment background thread is audited on the
  skunkBOX side, not here — see that repo's Phase 8 audit.)
- The one bulk-ish operation, `run_reconciliation()`'s per-remote-tenant
  upsert loop, commits and error-isolates one row at a time specifically
  so one bad/conflicting row can't roll back or block the others — see
  `app/services/tenant_sync.py`.

## Exports, reports, aggregates, counts
- No dashboard/report/export in this repo aggregates across
  Components/Datasets/Experiments/knowledge — Cophy holds no local copies
  of the first three at all, and the `Experiment` list page
  (`quality.list_experiments`) is a plain tenant-filtered `Experiment.query.filter_by(tenant_id=...)`
  with no cross-tenant aggregate anywhere in the query or template.
- Reporting (`app/routes/reporting.py`, audited above for the Tenant
  Separation PRD) was not touched by this PRD and does not reference any
  Components/Datasets/Experiments/knowledge data.

## Secret handling
- `SKUNKBOX_SERVICE_SECRET` is read only inside `app/skunkbox_client.py`'s
  `_secret()`, placed only in the outbound `X-Service-Secret` header, and
  never logged (`log.warning` calls in `_request()` log only
  `exc.__class__.__name__` on failure, never headers or the exception's
  full string in a way that could echo the secret) or passed to
  `render_template`/`flash`. `tests/test_cross_system_tenant_sync.py::test_secret_never_appears_in_logs_on_failure`,
  `tests/test_shared_knowledge_and_agents.py::test_service_secret_never_rendered_on_any_quality_page`
  (Phase 6) and `tests/test_ai_quality.py::test_service_secret_never_rendered_on_any_quality_page`
  (Phase 7) both assert this by configuring a known secret value and
  scanning every relevant page's response body for it.

## No global query hook (reconfirmed)
Same convention as the Tenant Separation audit above — every check in this
section is an explicit predicate, an explicit `abort(404)`/`require_tenant_record()`
call, or delegated to skunkBOX's own server-side enforcement. No ORM-level
global filter was introduced.

---

# Cross-System Tenant AI Assets — PRD Acceptance Mapping (Phase 8)

Maps `docs/prompts/Cross-System Tenant AI Assets - PRD.md` §16 (Security)
and §17 (Acceptance) to Cophy-side evidence. Full suite: 117 tests pass
(`.venv/bin/python -m pytest -q`). See `saas-platform`'s own Phase 8
documentation for the skunkBOX-side half of each criterion — most of these
are jointly enforced by both systems, and this table only speaks to the
Cophy side.

| PRD § | Criterion | Status | Cophy-side evidence |
|---|---|---|---|
| §16.1 | skunkBOX independently enforces tenant access | ✅ (skunkBOX-side, re-confirmed here) | Cophy never second-guesses a skunkBOX 404 with its own broader/narrower check — see "New/changed surfaces" above. |
| §16.2 | A Cophy tenant UUID alone is not authentication | ✅ | Every `skunkbox_client` call carries both the UUID *and* the service secret (`X-Service-Secret` + `X-Tenant-Id`); the UUID alone (e.g. a forged header on a request *to Cophy*) has no effect since Cophy never reads it from the request in the first place (see `get_active_tenant_external_id()` above). |
| §16.3 | A tenant API key cannot assert another tenant | N/A (skunkBOX-side enforcement; Cophy doesn't issue/validate `SkunkApiKey`) | — |
| §16.4 | A management service request cannot mutate shared Cofficiency resources for a customer | ✅ | Cophy's UI never exposes a mutation control on an `is_shared`/Shared row at all (Phase 6 templates hide edit/delete for `is_shared` `AiAgent`s and label Shared knowledge collections read-only); `app/routes/models.py` additionally rejects it server-side even if a form were forged. |
| §16.5 | Cross-tenant IDs/slugs/filters return 404 or safe denial | ✅ | `tests/test_ai_quality.py::test_cross_tenant_component_id_404s_on_read_and_every_mutation`, `test_cross_tenant_dataset_id_404s`, `test_cross_tenant_experiment_id_404s`; `tests/test_shared_knowledge_and_agents.py` (Phase 6 knowledge/agent equivalents) |
| §16.6 | Same-tenant validation applies to every relationship and worker job | ✅ | Experiment picker only offers same-tenant options (`test_experiment_picker_only_offers_same_tenant_resources`); no background worker exists Cophy-side (see above). |
| §16.7 | Shared collections/Agents are read/use only outside Cofficiency | ✅ | See §16.4 evidence; also `tests/test_shared_knowledge_and_agents.py::test_shared_agent_cannot_be_edited_or_toggled`. |
| §16.8 | Only Cofficiency can publish/unpublish shared resources | N/A (skunkBOX-side — the toggle lives in skunkBOX's admin UI, not Cophy) | — |
| §16.9 | Unsharing validates dependencies and active use | N/A (skunkBOX-side) | — |
| §16.10 | API logs record credential, actor, tenant, operation, target, outcome | Partial | Cophy's own `ApiRequestLog` (pre-existing, Tenant Separation PRD) records tenant/integration/endpoint/status for the *old* per-tenant chat/document path. The *new* `skunkbox_client.py` service-credential path has no equivalent Cophy-side log table yet — see the Observability section of the Phase 8 rollout doc for the gap and interim mitigation (skunkBOX's own `ApiRequestLog`/audit trail is the authoritative record for management-API calls either way, since it's the system actually executing them). |
| §16.11 | Tenant archival blocks new API operations without erasing history | ✅ (skunkBOX-side enforcement) + Cophy-side: an unsynced/inactive tenant is blocked from creating new portal users/agents (`app/routes/users.py`, `app/routes/models.py`, Phase 5) | `tests/test_cross_system_tenant_sync.py::test_cannot_add_portal_user_when_active_tenant_unsynced` |
| §16.12 | Cophy local mirror drift cannot grant access in skunkBOX | ✅ | Every skunkBOX call re-sends the tenant UUID and every mutation/read is re-validated by skunkBOX itself — a stale/incorrect local `Tenant.sync_status` or `AiAgent.is_shared` flag can only cause Cophy to show the *wrong UI state* (e.g. an offer to use an Agent that's since been unshared), never a successful unauthorized skunkBOX call, since skunkBOX independently re-checks visibility on every request regardless of what Cophy believed. |
| §17.5 | Customer A cannot see/use Customer B private resources | ✅ | See §16.5 evidence. |
| §17.6 | Customer tenants can see/use Shared Cofficiency collections and Agents | ✅ | `tests/test_shared_knowledge_and_agents.py::test_both_customers_see_shared_agent_neither_sees_others_private`, `test_both_customers_see_shared_collection_in_learning_center` |
| §17.7 | Customers cannot mutate shared resources | ✅ | See §16.4/§16.7 evidence. |
| §17.9 | A tenant Agent can combine tenant-private and Shared collections | Partial — verified at the skunkBOX/data level, not yet a Cophy UI feature | Combining collections on an Agent is a skunkBOX-side Persona configuration action (admin UI there); Cophy's Phase 6/7 scope is read/use, not authoring that association. Cophy correctly *displays* whichever collections a given Agent (owned or Shared) is already configured to use once Phase 9+/Components UI exposes it — no Cophy-side gap for the read path tested here. |
| §17.12 | Customers can complete the agreed Component/version/dataset/experiment workflow in Cophy | ✅ | `tests/test_ai_quality.py` (17 tests, full workflow); browser smoke test (Phase 7 CHANGELOG entry). |
| §17.13 | Background jobs and reports remain tenant-isolated | ✅ (N/A background jobs Cophy-side; reports unaffected — see above) | — |
| §17.14 | Tenant lifecycle changes converge between skunkBOX and Cophy | ✅ | Phase 5 reconciliation (`run_reconciliation()`, manual sync button, `flask sync-tenants` CLI); UUID cross-check in `docs/MIGRATION_REHEARSAL.md` §2.3 confirms convergence on the real dev databases of both systems. |
| §17.15 | Forged cross-tenant API requests fail inside skunkBOX | ✅ (skunkBOX-side, re-confirmed via Cophy's own tests hitting the fake client with forged ids and via the real API contract's documented 404 behavior) | — |
