# Changelog

## [2026-07-26] - Cross-System Tenant AI Assets Phase 7: Cophy Components, Datasets, and AI Quality management
- app/routes/quality.py (new blueprint `quality_bp`, `/quality/*`): customer-facing Components (AI Assets), Datasets, and Experiments/AI Quality management. Components/Datasets follow Learning Center's thin-proxy pattern exactly — no local copy of fields/versions/rows, every id passed straight through to skunkBOX with the server-resolved active tenant UUID, which independently 404s a cross-tenant or forged id
- app/skunkbox_client.py: added the full Components (list/get/create/update/promote/archive/reactivate/list_component_versions), Datasets (list/get/create/update/import_dataset_rows/archive), and Experiments (create/get/get_experiment_results) management-API calls, all service-credential + `X-Tenant-Id`
- app/models.py: new `Experiment` table — the *only* local row in this phase, and only because skunkBOX's management API has no `GET /experiments` list endpoint; stores skunkbox ids + who/when for a history list only, never status/progress/results (those stay live-fetched, per the PRD's "do not recreate ... evaluation state machines locally")
- migrations/versions/l2m3n4o5p6q7_add_experiment_table.py: creates the table; migrations/versions/m3n4o5p6q7r8_seed_ai_quality_nav_section.py: insert-only seed of a new "AI Quality" nav section (Components/Datasets/Experiments) — never wipes existing NavSection/NavItem rows, mirroring `e0ff5103a60e_add_tenant_management_nav_item.py`'s pattern rather than `h8i9j0k1l2m3`'s wipe-and-reseed one. Both applied to the real dev database after disposable-copy round-trip verification and a pre-migration backup
- app/page_registry.py: added `components`/`datasets`/`experiments` page slugs (standard view/edit permission levels, matching every other page — no separate "run" permission) and their nav entries, all gated on a single new `ai_quality` feature flag
- app/__init__.py: `ai_quality` feature flag seeded **off by default** (unlike every existing flag) — "Cofficiency can enable these incrementally per customer" per the phase brief — enabled per tenant via the existing Feature Flags override UI, no code change needed
- Experiment creation validates component version (must be Release/Production) and dataset version against the active tenant server-side (skunkBOX); the picker UI only offers same-tenant, eligible options. The status-poll endpoint re-derives the active tenant and re-checks local `Experiment` ownership on every call, so a tenant switch mid-poll 404s on the next tick instead of continuing to show stale progress
- Dataset row import: no multipart upload endpoint exists upstream (it's row-JSON only) — Cophy accepts a CSV file, parses it server-side (extension/size-checked, reusing the `_upload_attachment_to_skunkbox` validation pattern), and relays it as the JSON body skunkBOX actually expects; the service secret never reaches the browser
- Known, documented upstream limitation: skunkBOX's component response never echoes back `system_prompt`/`json_schema`/`json_formatting_requirements`/`release_notes` even though PATCH writes them — the edit form says so inline rather than silently looking broken. Similarly there's no model-id enumeration endpoint, so Experiment creation takes a manually-typed integer, the same established pattern as `AiAgent.skunkbox_agent_id`
- No hard-delete, optimizer, or internal-audit controls are exposed anywhere in the new UI — archive/reactivate (soft state) is the only lifecycle mutation, matching what the management API itself allows
- tests/conftest.py: extended `FakeSkunkBox` with full Components/Datasets/Experiments simulation (draft→release→production version state machine, `is_locked`, ownership checks, `seed_experiment()`); added `create_integration()`/`create_ai_agent()` helpers (added in the Phase 6 pass, used here too)
- tests/test_ai_quality.py (new, 17 tests): the complete agreed workflow (create/edit Component fields+prompt, draft→release→production promotion, create/import Dataset, run Experiment, view metrics/results, archive/reactivate), permission and feature-flag denial, cross-tenant ids on every mutation/read, switching mid-poll, idempotency-key presence on create/promote, safe backend-unavailable handling, no secret exposure, no delete/optimizer routes, and same-tenant-only Experiment picker options
- Fixed a latent test-fixture bug in the new `FakeSkunkBox`: `_versions_by_id` initially stored a shallow copy of the draft version dict rather than the same object referenced in the component's version list, so a promotion never became visible to `create_experiment()`'s lookup — fixed by storing one shared reference
- docs/ARCHITECTURE.md, docs/USER_MANUAL.md: documented the new proxy pattern, the `Experiment` mirror's rationale, and the two known upstream API gaps (write-only component fields, no model enumeration)
- Full suite: 117 tests pass (100 pre-existing + 17 new Phase 7 tests). Browser smoke test: feature flag defaults off and the nav section stays hidden until toggled on per-tenant via the existing Feature Flags UI (verified end-to-end, then reverted); all five new pages render cleanly with a safe error banner (not a crash) against a dev environment with no `SKUNKBOX_SERVICE_SECRET` configured
- Per the prompt's explicit scope: Phase 8 (cross-system audit and staged rollout) is not part of this phase

## [2026-07-26] - Cross-System Tenant AI Assets Phase 6: Cophy shared knowledge and Agent integration
- app/skunkbox_client.py: added `list_knowledge_collections()`, `get_knowledge_collection()`, `list_agents()`, `get_agent()` against skunkBOX's Phase 4 management API (service credential + new `X-Tenant-Id` header, resolved only via `tenant_context.require_active_tenant_external_id()`); `_request()` gained an optional `tenant_id` param — a second, disjoint auth path from the older per-tenant `Integration`/`X-API-Key` chat/document API, which has no document-content/search/download endpoint of its own and so remains in use for those
- app/models.py: `AiAgent` gains `is_shared` (marks a row as a system-managed mirror of a Cofficiency Shared skunkBOX Agent vs. a tenant's own hand-configured row) and a `(tenant_id, skunkbox_agent_id)` uniqueness constraint, so a tenant can never end up with two local rows pointing at the same skunkBOX agent
- migrations/versions/k1l2m3n4o5p6_add_ai_agent_is_shared.py: adds the column + constraint; aborts if any pre-existing `(tenant_id, skunkbox_agent_id)` duplicate is found rather than silently picking one (none existed); applied to the real dev database after a disposable-copy round-trip verification and a pre-migration backup
- app/services/agent_sync.py (new): `sync_shared_agents_for_tenant()` — upserts a local `AiAgent` mirror (`is_shared=True`, owned locally by the *customer* tenant, using that tenant's own "AI Agents" `Integration`) for every Cofficiency Shared Agent visible to a tenant; deactivates (never deletes) a mirror that's no longer visible; skips entirely if the tenant has no AI Agents Integration configured or isn't skunkBOX-synced; fails soft (never raises) on a skunkBOX outage. Run inline from `list_conversations()` on every view — same "always live, no persistence job" approach Learning Center already used for documents — rather than a new reconciliation command. Because the mirror's `tenant_id` is already the customer's own, no change was needed to `new_conversation()`/`send_message()`/ownership checks: a Shared Agent conversation is correctly owned by the customer tenant and uses the customer's own chat credentials by construction
- app/routes/models.py: `save_agent`/`toggle_agent` reject any mutation of an `is_shared=True` row ("managed by Cofficiency"); `add_agent`/`save_agent` reject creating/repointing a local agent at a `skunkbox_agent_id` already used by another local row for the same tenant (ambiguous-ownership guard, backed by the new DB constraint)
- app/routes/agents.py: `learning_center()` now fetches the collection tab list from the new management API (clean `is_shared`/`owner`/`can_edit`/`document_count` fields) instead of deriving an unlabeled list from document payloads; falls back to the old derivation if the tenant isn't synced or the management call fails, so browsing degrades gracefully rather than breaking
- Templates: added "Shared" badges (agent picker tiles, conversation header, Learning Center collection tabs/header/document rows, document detail page) and replaced the edit/deactivate menu with a "Managed by Cofficiency" label for `is_shared` rows in System Config → AI Agents
- tests/conftest.py: extended `FakeSkunkBox` with `seed_collection()`/`seed_agent()` and the four new management-API methods (visibility computed the same way as the real `tenant_id == caller OR is_shared` rule); added `create_integration()`/`create_ai_agent()` fixture helpers
- tests/test_shared_knowledge_and_agents.py (new, 10 tests): both customers see/use a Shared Agent and Shared collection while neither sees the other's private ones, Shared rows reject edit/toggle, the ambiguous-duplicate-ownership guard, a Shared Agent's conversation is owned by the customer's own active tenant, switching tenants invalidates a prior private conversation URL, document-proxy requests always use the currently-active tenant's own credentials (never a stale one), shared-agent sync and Learning Center both degrade safely (no raw exception, no 500) on a skunkBOX failure, and `ReleaseNote` remains tenant-agnostic (regression)
- Fixed a latent test-fixture bug surfaced by the new `ai_agent` uniqueness constraint: `test_tenant_phase4.py`'s `_make_agent()` hardcoded `skunkbox_agent_id=1` for every call, colliding with the legacy-fixture-seeded AdvantageFirst agent of the same id once uniqueness was enforced — now assigns a value unique per tenant
- docs/ARCHITECTURE.md: documented the new (second, disjoint) service-credential + tenant-UUID management API path alongside the existing per-tenant Integration path, and the Shared-Agent mirror design
- Full suite: 100 tests pass (90 pre-existing + 10 new Phase 6 tests)
- Per the prompt's explicit scope: no Components/AI Assets customer UI yet (Phase 7) — this phase is knowledge/Agent read access, Shared labeling, and tenant-safe propagation only

## [2026-07-26] - Cross-System Tenant AI Assets Phase 5: Cophy authoritative tenant synchronization
- app/models.py: `Tenant` gains `external_id` (immutable, unique, skunkBOX `public_id`), `sync_status` (`unsynced`/`synced`/`error`), `last_synced_at` — skunkBOX is now the authoritative tenant registry; Cophy's `Tenant` table is a synchronized local mirror keyed by UUID, not the source of truth
- migrations/versions/j0k1l2m3n4o5_add_tenant_external_id.py: backfills the real Cofficiency/AdvantageFirst UUIDs, then makes `external_id` NOT NULL + unique; refuses to guess a mapping for any other existing tenant (raises) unless `TENANT_SYNC_ALLOW_AUTO_UUID=1` is explicitly set for dev/test bootstrap; applied to the real dev database after a disposable-copy round-trip verification and a pre-migration backup
- app/skunkbox_client.py (new): focused HTTP client for skunkBOX's Phase 4 tenant provisioning API — `X-Service-Secret` auth (never logged), consistent `SkunkBoxClientError`, a single safe retry (network error/5xx, only for reads or idempotency-keyed writes, reusing the same key across the retry), idempotency keys for create
- app/services/tenant_sync.py (new): `upsert_tenant_from_remote()` (upsert-by-`external_id`, refuses to guess past a local name/slug collision — raises `TenantSyncError` instead), `run_reconciliation()` (fetch-all, per-row commit so one conflict doesn't block the rest, flags — never deletes — a local tenant skunkBOX didn't return, and only when the remote response was actually non-empty)
- app/routes/tenants.py: rewritten so create/edit/archive/reactivate call skunkBOX first and upsert the local mirror from its authoritative response — no local-only lifecycle mutation path; a post-authoritative local-mirror failure is reported as recoverable ("run reconciliation") rather than as if the whole operation failed; added a manual "Sync with skunkBOX" action
- app/cli.py (new): `flask sync-tenants` — same reconciliation logic as the in-app sync button, exit codes distinguish a fetch failure from conflicts/missing tenants, suitable for a scheduled job
- app/tenant_context.py: added `get_active_tenant_external_id()` / `require_active_tenant_external_id()` — the sanctioned way to resolve the active tenant's skunkBOX UUID, always server-side from the already-resolved active tenant, never from a request header/form field/query string; foundational plumbing for future customer-asset calls, not yet used by any of them
- app/routes/users.py, app/routes/models.py: block creating a portal user or an AI agent while the active tenant's `sync_status != "synced"`
- app/services/tenant_sync.py: `run_reconciliation()` now calls the previously-defined-but-unused `mark_sync_error()` helper for the missing-from-skunkbox case instead of inlining the same assignment; removed the resulting now-unused import from app/routes/tenants.py
- docs/ARCHITECTURE.md: rewrote the "skunkBOX interim boundary" section to document the new tenant-lifecycle authority split (skunkBOX authoritative / Cophy mirror) alongside the still-unchanged chat/attachment/knowledge-base boundary
- tests/test_cross_system_tenant_sync.py (new, 21 tests): UUID mapping migration, local ownership unchanged, skunkBOX-first create/edit/archive/reactivate (including skunkBOX rejecting a create with zero local rows created), idempotency-key reuse across an internal retry, idempotent recovery via reconciliation after a partial local-mirror failure, full reconciliation (create/update/flag-missing-without-deleting), empty-remote-response safety, name-collision drift detection, `User.tenant_id` never reassigned by reconciliation, archived-active-tenant fallback to Cofficiency driven by a sync, external/non-admin users blocked from every tenant-admin route, active UUID always server-resolved (a forged `X-Tenant-Id`/query param has no effect), service secret never appears in logs or rendered HTML, and the new unsynced-tenant user-creation guard
- Fixed two pre-existing tests broken by the skunkBOX-first route rewiring (`test_tenant_phase2.py::test_cofficiency_admin_can_create_archive_reactivate`, `test_tenant_adversarial.py::test_inactive_tenants_cannot_be_selected_or_receive_data`) to use the new `fake_skunkbox` fixture instead of assuming a local-only lifecycle
- Full suite: 90 tests pass (69 pre-existing + 21 new Phase 5 tests)
- Per the prompt's explicit scope: no customer-asset UI yet — this phase is schema, client, lifecycle UI, reconciliation, and the trusted-propagation foundation only

## [2026-07-24] - Tenant Separation Phase 6 (final): reporting, audit, and isolation hardening
- app/routes/reporting.py: LLM/Activity/API tabs now filter their base query, every derived aggregate (totals, error rate, average latency, total tokens, active-user count, top action), filter dropdowns, and pagination from one tenant-and-date-filtered query per tab — aggregates were previously calculated globally while the list was unfiltered; Activity now filters by `UserActivityLog.tenant_id`, not `User.tenant_id`
- app/activity_logger.py: added `reraise_if_testing()` — logging failures still fail safe in production, but now surface loudly under `current_app.testing` instead of silently vanishing; wired into all four log-writing except blocks (`log_activity`, both `_call_llm._log` closures, `agents._log_api`)
- docs/TENANT_ISOLATION_AUDIT.md (new): repository-wide audit of every `.query`/`filter_by`/`db.session.get`/`db.get_or_404`/bulk-update-delete site against each tenant-owned model, documenting what's tenant-scoped, what's intentionally global (and why), and what's explicitly deferred (Calls, Components, skunkBOX tenant-ID contract) — plus a full PRD §16–17 acceptance-criteria mapping table, including one honestly-flagged pre-existing gap (no CSRF protection anywhere in the app, not tenant-separation-specific)
- tests/test_tenant_adversarial.py (new): 15-scenario adversarial regression suite with a richer shared fixture (Cofficiency admin + a limited-permission Cofficiency non-admin + two customer tenants + one external user each + same-named config assets + conversations/attachments/logs/feature overrides in both tenants)
- docs/ARCHITECTURE.md: added a full "Tenant isolation" section (home vs. active tenant, model ownership table, authorization pattern, skunkBOX interim boundary, future Calls/Components/skunkBOX-tenant-ID requirements)
- docs/USER_MANUAL.md: added a "Tenant Switcher & Tenant Administration" section; updated Dashboard, Reporting, Users, Feature Flags, Models, and Roles & Permissions sections to describe tenant scoping instead of the old (now-incorrect) "global" behavior
- CLAUDE.md: First Run section now notes that `flask db upgrade` seeds the Cofficiency/AdvantageFirst tenants, and warns not to create real customer tenants before confirming the schema is fully migrated
- Final acceptance performed against the actual pre-tenant-migration backup of the real dev database (not just synthetic fixtures): row counts and ownership verified before/after upgrade, 3-way switching exercised (Cofficiency/AdvantageFirst/a new Customer C), confirmed zero cross-tenant leakage in rendered HTML, and confirmed release notes/quick-start remain reachable across every switch
- Full suite: 69 tests pass (10 Phase 1 + 12 Phase 2 + 11 Phase 3 + 12 Phase 4 + 11 Phase 5 + 15 Phase 6 adversarial)
- This completes Tenant Separation. Explicitly out of scope, per the PRD: Calls, Components/AI Assets, billing, tenant branding, tenant-specific roles, and the skunkBOX tenant-ID contract

## [2026-07-24] - Tenant Separation Phase 5: conversations, knowledge base, and dashboard
- **Critical fix**: `app/routes/agents.py` `new_conversation()` was never setting `AgentConversation.tenant_id` at all — since Phase 1 made that column required, every new conversation would either crash with an IntegrityError or (depending on ORM defaults) leave a row with no tenant. Now sets `tenant_id=agent.tenant_id` (already verified to equal the active tenant via `require_tenant_record`), satisfying the `AgentConversation.tenant_id == AiAgent.tenant_id == active_tenant.id` invariant.
- app/routes/agents.py `list_conversations()`: base conversation query, auto-cleanup of empty conversations, last-used-agent calculation, and the `all_users`/agent filter dropdowns are all now scoped to the active tenant — "Mine"/"All"/"Favorites" and their filters can no longer mix tenants, and a Cofficiency actor's "Mine" is filtered by both user ID and selected tenant.
- app/routes/agents.py: `view_conversation`, `archive_conversation` now call `require_tenant_record(conv)` (404 on cross-tenant, HTML routes); `send_message`, `upload_attachment`, `toggle_favorite` return a JSON 404 on cross-tenant instead (matching each route's existing JSON error contract) — a Cofficiency user can no longer keep a customer A conversation's URL open, switch to customer B, and keep using it.
- app/routes/agents.py `download_attachment`: added `AgentConversation.tenant_id == active_tenant` to the ownership join — previously only checked `conversation.user_id == current_user.id`, which a Cofficiency actor could satisfy across tenants; attachment ownership is now established through a same-tenant conversation, not just actor identity.
- app/routes/agents.py `_log_api()`: now attributes `ApiRequestLog.tenant_id` to the called integration's own owning tenant rather than re-resolving "whatever's active right now" — every call site already passes a same-tenant integration, so this ties the log to the resource actually called.
- app/routes/main.py, app/routes/reporting.py: dashboard operational counts (users/models/integrations/attributes) scoped to the active tenant; roles and release notes stay global (and are now labeled "Global" on both dashboard cards) — Reporting's own log/filter queries (LLM/Activity/API tabs) are left for Phase 6 per the phased plan.
- Learning Center and doc-generation LLM/integration selection were already tenant-scoped as of Phase 4; verified no agent selector exists in Learning Center to further scope, and that `help.py`'s release-notes/user-guide routes only ever query global `ReleaseNote`/`DocPrompt` rows.
- tests/test_tenant_phase5.py: 11 tests (Cofficiency + two customer tenants) covering agent-choice isolation, new-conversation tenant assignment, forged cross-tenant agent IDs, mine/all/favorites separation, the stale-URL-after-switch scenario, cross-tenant send/archive/favorite/upload/download rejection, attachment ownership via conversation tenant, knowledge-base integration isolation, outbound API log tenant attribution, tenant-varying dashboard counts, and global roles/release-notes/docs invariance
- Audited identifier-based routes in `app/routes/agents.py`: `list_conversations` (agent/user filters), `new_conversation` (agent_id), `view_conversation`, `send_message`, `upload_attachment`, `download_attachment` (attachment_id via conversation join), `toggle_favorite`, `archive_conversation`, `learning_center`/`learning_center_doc`/`learning_center_file` (integration-scoped, no local doc IDs to check) — all now tenant-safe
- No schema changes this phase — full suite (54 tests) passes; verified the `new_conversation` fix against a disposable copy of the real dev database (agent tenant_id correctly propagated to the new conversation)

## [2026-07-24] - Tenant Separation Phase 4: tenant-isolated configuration and feature flags
- app/routes/models.py: `LlmModel`, `Attribute`, `Integration`, and `AiAgent` list/create/update/toggle/batch operations now scope to the active tenant; duplicate-name checks and default-model clearing are per-tenant; creates require an active (non-archived) tenant and bind `tenant_id` server-side only; direct-ID routes call `require_tenant_record()`; agent create/update reject an `integration_id` that doesn't belong to the active tenant; agent deactivation's conversation-archiving predicate includes `tenant_id` for defense-in-depth
- app/feature_flags.py: new resolver — `effective_feature_flags(tenant=None)` / `is_feature_enabled(key, tenant=None)` — global `FeatureFlag` catalogue with `TenantFeatureFlag` override applied; wired into `inject_feature_flags`/`inject_nav` in `app/__init__.py` (previously read `FeatureFlag.is_enabled` directly)
- app/routes/models.py: `toggle_flag` now writes/updates a `TenantFeatureFlag` row for the active tenant instead of mutating the global `FeatureFlag` row; added `reset_flag` to remove a tenant's override and revert to the global default
- app/templates/models/list.html: Feature Flags tab shows Global Default vs. Effective-for-this-tenant with an Inherited/Overridden badge and a Reset button; added a tenant-context banner across the tenant-scoped tabs; labeled Sections/Help Prompts tabs "(Global)"
- app/access.py: added `feature_required(key)` — a disabled feature's route rejects direct access even when its nav item is hidden; applied to all conversations routes and learning-center routes (`app/routes/agents.py`) and the system-overview routes (`app/routes/help.py`)
- app/routes/agents.py: the "start a new conversation" agent picker and `new_conversation`'s `agent_id` validation now scope to the active tenant (`require_tenant_record`); `_get_docs_integration()` scoped to active tenant
- app/doc_generator.py, app/release_manager.py, app/routes/help.py: LLM-model-selection helpers (release notes, doc generation, prompt-improvement) now resolve within the active tenant's `LlmModel` rows instead of picking a default across all tenants
- Kept explicitly global, unchanged: `Role`, `Permission`, `ReleaseNote`, `NavSection`/`NavItem`, `DocPrompt`, and the `FeatureFlag` catalogue rows themselves
- No skunkBOX API contract change — isolation stays indirect via tenant-owned integrations/agents, per this phase's interim boundary
- tests/test_tenant_phase4.py: 12 new tests (3-tenant fixture) covering cross-tenant name reuse/duplicate rejection, list isolation, forged-input resistance, cross-tenant update/toggle/batch rejection, default-model isolation, agent/integration cross-tenant rejection, agent-deactivation conversation-archiving isolation, flag inheritance/override/nav-route consistency, and global-entity invariance
- No schema changes this phase (tenant_id/TenantFeatureFlag already existed from Phase 1) — full suite (43 tests) passes; verified live in-browser (tenant banner, Feature Flags tab, tenant switcher) against a disposable copy of the real dev database

## [2026-07-24] - Tenant Separation Phase 3: tenant-isolated user management
- app/routes/users.py: `list_users` and its per-role counts now filter by the active tenant; `add_user` assigns `tenant_id` from the server-resolved active tenant only (never read from the request) and rejects creation when the active tenant isn't active; `edit_user`, `toggle_user`, and the admin `upload_avatar` route now call `require_tenant_record()` right after fetching the target — a cross-tenant `user_id` 404s before any data is read or mutated
- app/models.py: clarified the `User.tenant_id` comment — no route may update it; correcting a user's home tenant requires a controlled data migration, not ordinary UI
- app/templates/users/edit.html: added a read-only "Tenant" field (edit only, never on add) so it's visible which tenant a user belongs to
- app/templates/users/list.html: shows "Showing users in {tenant}" for Cofficiency users so it's clear which tenant's users are listed
- User-query audit (see chat for full classification): `users.py`'s list/edit/toggle/avatar routes are the only tenant-scoped operational sites and are now all scoped; `auth.py` login and the Flask-Login `user_loader` are global identity lookups and correctly untouched; username/email uniqueness checks and role-rename/delete bulk updates in `permissions.py` are intentionally global (username/email and roles are global); the conversations "All Conversations" user filter (`agents.py`) and Reporting's user filter/dashboard count (`reporting.py`, `main.py`) are tenant-scoped surfaces not addressed here — recorded for Phase 5 (conversations) and Phase 6 (reporting/dashboard) respectively
- tests/: found and fixed a test-infrastructure bug in the `full_app` fixture — it held a persistent outer app context across the whole test, which Flask silently reuses for every `client.*()` call (same app → same `flask.g`), resurrecting tenant_context's per-request cache across what should be independent requests; removed the persistent context so each request gets its own, matching real request behavior
- tests/test_tenant_phase3.py: 11 new tests (3-tenant fixture: Cofficiency, AdvantageFirst, a third customer tenant) covering list/count isolation, switch-then-list, external-user isolation, tenant_id assignment/forgery resistance, cross-tenant edit/toggle/avatar rejection, global username/email/role behavior, and activity attribution
- No schema changes this phase — full suite (31 tests) passes; verified live against a disposable copy of the real dev database

## [2026-07-24] - Tenant Separation Phase 2: active tenant context, switcher, tenant admin
- app/tenant_context.py: new central resolver — `is_cofficiency_user`, `get_cofficiency_tenant`, `get_active_tenant(_id)`, `can_switch_tenants`, `require_tenant_record`; external users always resolve to home tenant, Cofficiency users resolve to `last_active_tenant_id` (falling back to Cofficiency if null/invalid/inactive), cached once per request via `flask.g`
- app/routes/tenants.py: new blueprint — `POST /tenants/switch` (Cofficiency-only, persists `last_active_tenant_id`, never touches `tenant_id`, logs `tenant.switched` under the destination tenant, safe-redirect validated) and Cofficiency-admin-only tenant CRUD (`/tenants/`, add/edit/archive/reactivate); protected Cofficiency tenant cannot be renamed or archived
- app/access.py: added `cofficiency_admin_required` — checks home-tenant identity directly rather than relying on `is_admin()` role-bypass alone, so an external tenant's own admin-role user can't manage other tenants
- app/templates/base.html: header tenant switcher (dropdown, active tenant name, checkmark on current selection) placed left of the avatar, Cofficiency users only
- app/page_registry.py, app/templates/tenants/list.html, migrations/versions/e0ff5103a60e_...: new "Tenant Management" page/nav entry (Administration section, Cofficiency-only visibility)
- app/activity_logger.py, app/routes/agents.py, app/release_manager.py, app/doc_generator.py: `log_activity()` and the LLM/API request log writers now stamp the actor's resolved *active* tenant (not home tenant) at event time; a Cofficiency user working in another tenant produces activity for that tenant
- migrations/versions/b76334d75376_...: fixed a pre-existing, unrelated bug found while testing from a fresh install — migration `11b469c6d972` was titled "add scope to permission" but never actually added the column (real DBs had it out-of-band); this adds it, guarded to no-op where already present
- tests/: added `full_app`/`client` fixtures (real app + blueprints, vs. the bare Phase 1 fixture) and 12 Phase 2 tests covering switch/permission/attribution/tenant-admin scenarios; verified manually via browser (switcher dropdown, tenant admin page, external-user rejection) against a disposable DB copy
- Tenant isolation for user lists, configuration, conversations, dashboards, and reporting is still not enforced — that's Phase 3+

## [2026-07-24] - Tenant Separation Phase 1: schema and safe migration
- app/models.py: added `Tenant` and `TenantFeatureFlag` models; added `tenant_id`/`last_active_tenant_id` to `User`; added required `tenant_id` to `LlmModel`, `Attribute`, `Integration`, `AiAgent`, `AgentConversation`, `LlmRequestLog`, `UserActivityLog`, `ApiRequestLog`; converted `LlmModel`/`Attribute`/`Integration` uniqueness to tenant-relative
- migrations/versions/7f7733a2f7d0_...: hand-written migration — creates `tenant`, seeds protected Cofficiency + AdvantageFirst, backfills existing `admin` user to Cofficiency (remembered tenant AdvantageFirst) and every other user/operational record/historical log to AdvantageFirst, replaces global uniqueness with tenant-relative constraints, makes tenant columns non-null; includes a full downgrade
- app/__init__.py: seed guards now wait for the tenant schema and seeded Cofficiency/AdvantageFirst rows before running; fresh-install admin seeds to Cofficiency, default attributes seed to AdvantageFirst
- tests/: added migration/model test suite (10 cases) covering tenant seeding, historical ownership backfill, non-null enforcement, tenant-relative uniqueness, and relationship loading; added pytest to requirements.txt
- No tenant switcher or tenant-aware route behavior yet — that's Phase 2+

## [2026-06-02] - Permissions: Own/All scope for Conversations + View/Edit distinction
- app/models.py: added `scope` column (own/all) to Permission model; added get_scope() helper to Role
- app/access.py: added get_user_scope() helper
- app/page_registry.py: marked conversations as scoped: True; added conversations and learning_center to PAGES; updated labels to match nav (User Management, System Config, User Guides, etc.)
- app/routes/permissions.py: save_role now reads and persists scope for scoped pages
- app/routes/agents.py: split conversations routes into view (list, view, download, favorite) and edit (new, send, upload, archive); enforce scope — own-scoped users cannot access All tab or other users' conversations; added get_user_scope import
- app/templates/users/list.html: permissions edit modal shows Own/All scope toggle for Conversations; summary table shows scope pill next to page name in Edit/View columns
- app/templates/agents/list.html: All Conversations tab hidden when user scope is own
- app/static/css/style.css: added .perm-toggle-scope and .scope-pill styles

## [2026-06-02] - Fix 403 on AI Conversations for admin users
- app/routes/agents.py: relaxed ownership checks in view_conversation, send_message, upload_attachment, toggle_favorite, and archive_conversation to allow admin users to access any conversation

## [2026-05-29] - AI Agents: Show Inactive toggle, auto-archive on deactivate, conversation safety filter
- app/templates/models/list.html: added "Show Inactive" toggle to AI Agents Config header (OFF by default); inactive agent rows hidden on load via data-active attribute; fixed toggle CSS class (toggle-track, not toggle-slider)
- app/templates/models/list.html: added id="agents-tbody" and data-active="{{ agent.is_active }}" to agent rows
- app/static/js/app.js: added filterInactiveAgents() following same pattern as filterInactive() and filterInactiveApis()
- app/routes/models.py: toggle_agent() now bulk-archives all non-archived conversations for an agent when it is deactivated; flash message reports count of archived conversations
- app/routes/agents.py: list_conversations() base query joins AiAgent and filters AiAgent.is_active == True across all tabs (My, All, Favorites) as a permanent safety net

## [2026-05-29] - Generate Release Notes modal: darker backdrop
- app/templates/help/release_notes.html: backdrop opacity increased from rgba(0,0,0,0.45) to rgba(0,0,0,0.7) for visibility on dark theme

## [2026-05-10] - Doc Prompt Editor Phase 1: editable help-doc prompts with AI-assisted improve flow
- app/models.py: added DocPrompt model (key, label, prompt_text, timestamps)
- migrations/versions/1bdbff5ce391: creates doc_prompt table
- app/doc_generator.py: replaced _SYSTEM_PROMPT constant with DEFAULT_PROMPTS dict; added _get_doc_prompt() DB-backed helper; simplified three generators to use _get_doc_prompt()
- app/__init__.py: imports DocPrompt; table guard added; seeds four default prompts on startup
- app/routes/models.py: added DocPrompt import; list_models() passes doc_prompts + default_prompts to template; added save_doc_prompt and reset_doc_prompt routes
- app/routes/help.py: added log_activity import; added improve_doc_prompt (POST /help/improve/<doc_key>) and apply_improved_prompt (POST /help/improve/<doc_key>/apply) routes for AI-assisted prompt editing
- app/templates/models/list.html: added "Help Prompts" tab with editable textarea + Save/Reset per prompt
- app/templates/help/doc_page.html: added "Improve this doc" button and three-step modal (instruction → AI review → apply/regenerate)

## [2026-05-10] - Fix Generate Release Notes: always shows only new entries
- app/models.py: added changelog_snapshot (TEXT) column to ReleaseNote
- app/routes/help.py: generate_release() saves CHANGELOG.md text snapshot at publish time
- app/routes/help.py: changelog_preview() diffs against snapshot instead of git commit hash
- migrations/versions/b543b16784f2: adds column + backfills v1.0.0 snapshot so next generation shows only post-v1.0.0 entries

## [2026-05-10] - My Conversations: agent tiles become a ribbon on overflow
- app/templates/agents/list.html: tiles stay full-size (268×303px); overflow:hidden + translateX ribbon with ‹ › arrows activates only when tiles exceed available width
- app/templates/agents/list.html: arrows hidden when all tiles fit; re-evaluated on window resize

## [2026-05-10] - Allow sending attachment-only messages (no text required)
- app/routes/agents.py: removed hard "message is empty" block when attachment_ids are present
- app/routes/agents.py: skunkBOX receives "[File attached — please review]" placeholder when content is empty
- app/routes/agents.py: conversation auto-title falls back to attachment filename when no text

## [2026-05-10] - New Conversation modal: ribbon picker, wider, auto-select
- app/templates/agents/list.html: modal is 25% wider (780→975px)
- app/templates/agents/list.html: agent picker replaced with horizontal ribbon with left/right arrows; agents already sorted by last-use from route
- app/templates/agents/list.html: first agent auto-selected on modal open; arrows hidden when all tiles fit

## [2026-05-10] - New Conversation modal: attachment support
- app/routes/agents.py: new_conversation() returns JSON when X-Requested-With: XMLHttpRequest so modal can get conv_id before navigating
- app/templates/agents/list.html: added paperclip button, file input, attachment chips, and async submitNewConv() that creates conv then uploads files
- app/templates/agents/conversation.html: auto-send IIFE now restores staged modal attachments from sessionStorage before sending the first message

## [2026-05-09] - Conversation attachments — historical chips & dynamic bubble chips (Phase 5)
- app/templates/agents/conversation.html: added Jinja2 attachment chips above message text for both user and assistant historical bubbles
- app/templates/agents/conversation.html: added CSS .attach-chip-history with hover state for download links
- app/templates/agents/conversation.html: added buildAttachmentChipsHtml() JS helper for dynamic bubble chips
- app/templates/agents/conversation.html: appendUserBubble() now accepts attachments arg and prepends chips HTML
- app/templates/agents/conversation.html: sendMessage() captures sentAttachments before clearing pendingAttachments and passes to appendUserBubble()
- app/routes/agents.py: view_conversation passes attachments_by_message_id dict to template (Phase 5 Step 1)

## [2026-05-09] - Conversation attachments chat UI — attach & send (Phase 4)
- app/templates/agents/conversation.html: added paperclip button (left of send), hidden file input, and attachment chips area above input bar
- app/templates/agents/conversation.html: added CSS for .attach-chip, chip sub-elements, error state, #attach-btn hover, and @keyframes spin
- app/templates/agents/conversation.html: added JS — pendingAttachments/uploadsInProgress state, file picker wiring, handleFileSelected() with spinner→resolved chip flow, image thumbnail preview, truncate/showErrorChip/removeAttachment/updateChipsVisibility/updateSendButton helpers
- app/templates/agents/conversation.html: modified sendMessage() to include attachment_ids + attachment_metadata in request body and clear chips on success

## [2026-05-09] - Conversation attachments upload proxy and local storage (Phase 3)
- app/models.py: added MessageAttachment model (local metadata mirror; file lives on skunkBOX)
- migrations/928c0eaef896: migration for message_attachment table
- app/routes/agents.py: added _upload_attachment_to_skunkbox() helper with size/extension validation
- app/routes/agents.py: added POST /agents/<conv_id>/attachments upload proxy route
- app/routes/agents.py: added GET /agents/attachments/<id>/download ownership-checked proxy route
- app/routes/agents.py: send_message now accepts attachment_ids + attachment_metadata, forwards ids to skunkBOX, saves MessageAttachment rows after commit

## [2026-05-08] - UI polish + skunkBOX API logging

### Bug fixes
- **All Conversations filters** — replaced native `<select multiple>` list boxes with custom dropdown multi-selects for Agent and User; trigger shows "All agents" / "N selected"; checkboxes inside a styled panel; closes on outside click; sticky selection state preserved
- **Learning Center rate limit fix** — eliminated double API call on list page; now makes a single `limit=500` fetch and handles collection filtering + pagination entirely in Python, staying within the 10 RPM rate limit
- **AI Agents Config** — agent logo now renders as a clean round circle, matching the Conversations list; image wrapped in `overflow:hidden` div instead of relying on `border-radius` on the `<img>` tag alone

### External API request logging
- `_call_skunkbox_get()` and `_call_skunkbox()` in `agents.py` now write one `ApiRequestLog` row per call with `integration_id`, `integration_name`, `endpoint` (full URL), `method`, `status_code`, `latency_ms`, and `error_message`
- New `_log_api()` helper wraps the DB write in try/except so a logging failure never breaks the API call
- All skunkBOX traffic (chat messages, document list, document detail) now appears in Reporting → External API Requests

## [2026-05-08] - Learning Center collection tabs

### Feature
- Removed "Conversations" tab from the Learning Center tab bar
- Added **All Documents** as the first tab (shows all docs across all collections, includes Collection column)
- Added one tab per document collection, sorted A-Z — tabs are discovered dynamically by scanning the documents API response (no separate collections endpoint required)
- Collection column hidden when viewing a specific collection tab (redundant in that context)
- Pagination links now carry `?tab=<id>&page=N` so the active tab is preserved when paging
- `learning_center()` route makes one broad fetch (`limit=500`) to build the collections list, then a separate paginated fetch filtered by `collection_id` for the active tab

## [2026-05-08] - Navigation restructure + Conversations filter panel

### Home page change
- **Conversations (My Conversations) is now the default home page** — `/` and post-login redirect to `agents.list_conversations` instead of the old Dashboard
- All breadcrumb "Home" links and fallback redirects across every route file updated accordingly

### Dashboard moved to Reporting
- Dashboard removed from the left sidebar navigation
- Dashboard content (stat cards + Recent Release Notes) added as the **first tab** ("Dashboard") in the Reporting section (`/reporting/?tab=dashboard`)
- Reporting now defaults to the Dashboard tab
- `reporting.py` imports `Attribute`, `Role`, `ReleaseNote`; queries and passes `dash_stats` and `recent_releases` to the template
- Reporting tab bar switched to `tax-tab` / `tax-tabs` CSS pattern for consistency

### All Conversations filter panel
- Agent tiles hidden on the "All Conversations" tab
- Filter panel added (card with three controls): **Agent** multi-select, **User** multi-select (current user listed first as "My Conversations"), **Date Range** (from/to date pickers)
- **Apply** button submits filters via GET; **Clear** button appears only when filters are active
- Filter state is sticky (pre-selected after submit)
- `list_conversations()` in `agents.py` reads `agent_ids`, `user_ids`, `date_from`, `date_to` params and applies them to the query when `tab == "all"`; passes `all_users` and current filter state to template
- Date-to filter includes the full end day (23:59:59)
- Improved empty states: tab-aware messaging for Favorites, filtered All Conversations, and no-agent state

### Conversations — star / favorites
- Added `is_favorite` boolean column to `AgentConversation` (migration `75c0ec3212cc`)
- Star toggle button per conversation row; AJAX `POST /agents/<id>/favorite` flips the flag and returns JSON
- Three-tab navigation: **My Conversations** / **All Conversations** / **⭐ Favorites**
- Tab title shown as `<h1>` below the tab strip (matches User Management pattern)

### New Conversation modal
- "New Conversation" button in the top-right of the page header
- Modal with agent tile picker + large question textarea
- Agent auto-selected when only one exists; initial message passed as `?q=` param and auto-sent on conversation load

## [2026-05-07] - Learning Center

### Feature
- Added **Learning Center** tab to the AI Agents section (alongside Conversations)
- New routes in `agents.py`: `learning_center()` and `learning_center_doc(doc_id)`
- `_get_docs_integration()` — finds the active integration with `use_case = "Documents"`
- `_call_skunkbox_get()` — generic GET helper to skunkBOX API (same URL normalisation as chat)
- **List view** (`/agents/learning-center`): document table with file-type icon, title, collection, type badge, status badge, pages, upload date; pagination at 25/page with smart page-number range
- **Detail view** (`/agents/learning-center/<doc_id>`): two-column layout — preview panel (text `content_preview`, PDF iframe, image, or "no preview" fallback) + full metadata panel showing all fields returned by the API (known fields with friendly labels first, then any extras auto-labelled from the key name)
- Empty state if no Documents integration is configured, with link to External APIs config
- Sidebar AI Agents nav link stays highlighted on both Learning Center routes

## [2026-05-07] - Integration Use Case field

### Feature
- Added `use_case` column to `Integration` model (`String(40)`, default `"AI Agents"`)
- Added Alembic migration `c2d3e4f5g6h7_add_integration_use_case.py` (chains off `b1c2d3e4f5g6`)
- Add / Edit Integration modals now include a required **Use Case** dropdown with two options: `AI Agents` and `Documents`
- Use Case displayed as a colour-coded badge in the External APIs table (green for AI Agents, purple for Documents)
- Routes `add_integration` and `save_integration` in `models.py` now read and persist `use_case`

## [2026-05-07] - Activity logging for conversations, user management, system config

### Activity logging
- Added `log_activity` calls to `app/routes/users.py`: user created, updated, password changed, activated, deactivated
- Added `log_activity` calls to `app/routes/agents.py`: conversation started, archived
- Added `log_activity` calls to `app/routes/models.py`: LLM model created/updated/activated/deactivated, integration created/updated, AI agent created/updated/activated/deactivated, attributes saved
- Expanded `ACTION_LABELS` in `app/activity_logger.py` to cover all new action keys

## [2026-05-07] - Attributes Edit button fix

### Bug fix
- Fixed broken Edit button in System Config > Attributes: `{{ category | tojson }}` inside a double-quoted `onclick="..."` attribute produced unescaped `"` characters that truncated the HTML attribute value, silently breaking the JS call. Changed attribute delimiter to single quotes: `onclick='openAttrModal({{ category | tojson }})'`
- Removed stale inner `tax-tabs` strip from the Attributes section (leftover from before the 4-tab top-level strip was added)
- Removed stale Jinja `{% if can_view_models or can_view_integrations %}style="display:none"{% endif %}` from `config-tab-attributes` div — show/hide is now handled entirely by `switchTopTab()` JS, consistent with all other sections

## [2026-05-07] - AI Agents feature + UI polish

### AI Agents feature
- Added `AiAgent`, `AgentConversation`, `AgentMessage` models to `app/models.py`
- Added Alembic migration `b1c2d3e4f5g6_add_ai_agents.py` (chains off `a1b2c3d4e5f6`)
- Added `agents` page slug to `page_registry.py`; seeded into all existing roles on startup
- Added `AGENT_AVATAR_UPLOAD_FOLDER` config key; directory created on app startup
- Added `agents_bp` blueprint (`app/routes/agents.py`) with routes: list conversations, new conversation, view conversation, send message (AJAX → skunkBOX API), archive conversation
- skunkBOX API call: `POST {base_url}/api/v1/chat/messages` with `X-API-Key` header, `persona_id` / `message` / `session_id` body; `skunkbox_session_id` persisted for thread continuity
- Added `app/templates/agents/list.html` — conversations list with "New Conversation" agent-picker overlay
- Added `app/templates/agents/conversation.html` — chat UI with auto-grow textarea, Enter-to-send, `marked.js` markdown rendering, typing indicator animation
- Added AI Agents CRUD to `app/routes/models.py`: `add_agent`, `save_agent`, `toggle_agent` with avatar file upload
- Added "AI Agents Config" tab to System Config (`models/list.html`) — agent table with avatar, integration reference, skunkBOX Agent ID; add/edit modals with file upload
- Added `robot`, `message`, `send` icons to `macros/ui.html`
- Added `requests==2.32.3` to `requirements.txt`

### Navigation changes
- "AI Agents" sidebar section moved to sit directly below Dashboard, above Administration
- "Configure Agents" removed as a standalone nav item — accessible only as a tab within System Config
- System Config now defaults to AI Agents Config tab (no hash or `#agents`); `#integrations` and `#attributes` still navigate directly to their sections

### UI polish
- Breadcrumb separator changed from `>>` to ` > `
- Added chat bubble CSS to `style.css`: user/agent bubble layout, markdown-in-bubble styles, typing dots bounce animation

## [2026-05-06] - Documentation + sidebar + LLM Models UI

### Documentation restructure
- Split help section into two pages: User Guides (Release Notes, Quick Start, User Manual) and System Overview (Architecture, Python Dependencies)
- Added `sb-page-header` with title and description below tab strip on each doc page
- Added three-level breadcrumbs to all documentation pages
- Stripped leading `# H1` from markdown files in `_render_doc()` to prevent duplicate headers
- Added `md` Jinja2 template filter for markdown → HTML conversion

### Release Notes
- Switched to three-tier card pattern: Major (green), Minor (blue), Patch (grey)
- Card UI uses CSS variables for full dark-mode support

### Sidebar collapse
- Sidebar collapses/expands by clicking the brand mark; state persisted in `localStorage`
- Section labels replaced by gray separator lines in collapsed state
- Nav labels hidden in collapsed state; icon position unchanged
- Floating tooltip shown on icon hover when sidebar is collapsed

### LLM Models table
- Status badges: `badge-active` (green), `badge-inactive` (red), `badge-default` (purple)
- Deactivate/Reactivate via global `confirmAction` modal added to `base.html` (Escape key supported)

## [2026-05-06] - Initial cleanup — align with skunkBOX principles

- Removed unauthenticated `/bootstrap/reset-admin` endpoint (security hole)
- Fixed deprecated SQLAlchemy patterns: `Model.query.get()` → `db.session.get()`, `get_or_404()` → `db.get_or_404()`
- Added `is_admin()` method to User model — use instead of `role == "admin"` string comparison
- Added `updated_at` column to User, Role, and LlmModel models
- Added `last_login` column to User model; populated on successful login
- Initialized Flask-Migrate; created initial schema migration (`db2364c230d4`)
- Removed `db.create_all()` from app factory — schema now managed via migrations
- Added schema guard to `_seed_defaults()` so it skips gracefully before `flask db upgrade` is run
- Extracted shared permission helper `user_has_access()` to `app/access.py` — eliminates duplicate logic in models route and `__init__.py` context processor
- Passed `PAGES` from routes to templates — no more hardcoded page lists in Jinja
- Added `.local-time` UTC→local timestamp conversion pattern to all templates (matches skunkBOX convention)
- Added UTC→local JS handler to `app.js`
- Created `CLAUDE.md` with project conventions aligned with skunkBOX
- Fixed `DESIGN_SYSTEM.md` — CSS variable names now match the actual `style.css`
