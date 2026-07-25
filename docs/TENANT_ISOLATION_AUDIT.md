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
- **Components / AI Assets**: blocked on a tenant-aware skunkBOX management API that doesn't exist yet.
- **skunkBOX tenant-ID contract**: isolation remains indirect (tenant-owned Integration credentials) by design; no speculative tenant field is sent to skunkBOX.

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
| 5 | Tenant switching accepts only active tenants; CSRF-protected per project conventions | ⚠️ Partial | `switch_tenant()` validates `Tenant.query.filter_by(id=target_id, is_active=True)` — an inactive or nonexistent target is rejected (`tests/test_tenant_phase2.py::test_cofficiency_user_default_resolution`, `test_tenant_adversarial.py::test_inactive_tenants_cannot_be_selected_or_receive_data`). **CSRF**: this repository has no CSRF middleware anywhere (no Flask-WTF, no token on any form) — "according to project conventions" is satisfied literally (the switch form matches every other POST form in the app), but the *project itself* has no CSRF protection to inherit. Flagging as a pre-existing, repository-wide gap rather than silently claiming coverage that doesn't exist. |
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

## Known gap to carry forward

**CSRF protection is repository-wide absent**, not specific to tenant
separation — no form anywhere in this codebase (including pre-existing ones
like login, user edit, or role save) carries a CSRF token, and no Flask-WTF
or equivalent middleware is installed. The tenant-switch endpoint matches
this existing (missing) convention exactly rather than introducing a
one-off inconsistency. Adding CSRF protection is a cross-cutting change
affecting every POST form in the app and is out of scope for tenant
separation; flagging it here so it isn't mistaken for a tenant-specific gap.
