# Phase 6 — Reporting, Audit, and Isolation Hardening

You are working on `saas-mortgage` (Cophy Portal).

Read:

- `docs/prompts/Tenant Separation - PRD.md`
- Completed Phases 1–5
- All route, model, logging, reporting, dashboard, and template code
- Existing architecture and user documentation
- Any repository agent instructions

Implement Phase 6 as the final tenant-separation hardening phase.

---

## Goal

Finish tenant-isolated reporting, audit every data-access path, add adversarial regression coverage, and update documentation so tenant separation is safe to enable for customer tenants.

---

## Reporting

Filter all reporting data and summaries by `active_tenant.id`:

### LLM requests

- Base query
- Totals/errors/error rate
- Average latency
- Total tokens
- Model filter choices
- Pagination

Ensure aggregate queries use the same tenant/date/filter predicates as the list. Do not calculate totals globally while displaying a tenant-filtered list.

### User activity

- Base query
- Totals and active-user count
- Top action
- User filter choices
- Pagination

The actor may belong to Cofficiency while the event belongs to the selected customer tenant. Filter by `UserActivityLog.tenant_id`, not `User.tenant_id`.

### External API requests

- Base query
- Totals/errors/error rate
- Average latency
- Integration filter choices
- Pagination

Filter by the log row's stored tenant ID. Do not infer historical tenant through the current integration or actor because records/configuration may later change.

### Reporting dashboard

- Tenant-owned cards use active-tenant counts.
- Global role/release-note data may remain global but must be labeled/handled consistently with the main dashboard.
- Recent release notes remain global.

Reporting remains subject to existing admin/permission behavior. Cofficiency switching does not bypass it.

---

## Logging completion

Audit all `UserActivityLog`, `LlmRequestLog`, and `ApiRequestLog` constructors and helpers.

Required:

- Every new row gets a non-null event-time tenant ID.
- Request-handling paths use resolved active/owning tenant.
- A background/global documentation or release process must receive explicit tenant context from the initiating request where applicable.
- Do not fall back to the actor's home tenant when a valid active tenant exists.
- No swallowed logging exception should conceal a schema/programming bug during tests; retain production fail-safe behavior while making tests observable.

Add/verify `tenant.switched` in activity labels.

---

## Full isolation audit

Use repository-wide searches for:

- `.query`
- `query.get`
- `filter_by`
- `db.session.get`
- `db.get_or_404`
- bulk `.update()` / `.delete()`
- raw SQL
- foreign-key IDs from forms/JSON/query parameters

For every occurrence involving a tenant-owned model, confirm:

1. List queries filter active tenant.
2. Creates assign tenant server-side.
3. Direct reads/mutations validate tenant.
4. Related records belong to the same tenant.
5. Bulk operations include tenant.
6. Dropdown/filter data is tenant-limited.
7. Aggregates and exports are tenant-limited.

Document the audit in a concise markdown checklist under `docs/`, including files/surfaces reviewed and any intentionally global queries.

Do not introduce a global SQLAlchemy tenant filter unless the codebase has a thoroughly tested, migration-safe pattern for bypassing it. Explicit predicates and shared helper functions are preferred for auditability.

---

## Adversarial tests

Build a tenant-isolation regression suite using:

- One Cofficiency admin
- One Cofficiency non-admin with limited permissions
- Two customer tenants
- At least one external user per customer
- Same-named configuration assets in both customer tenants
- Conversations, attachments, logs, and feature overrides in both tenants

Test:

1. External user cannot switch tenant through POST, forged session/cookie state, or query parameter.
2. Tenant assignment cannot be changed through crafted user forms.
3. Cross-tenant IDs fail for every read/mutation route.
4. Bulk operations cannot affect another tenant.
5. Cross-tenant agent/integration references fail.
6. Switching invalidates access to previously open tenant URLs.
7. Limited Cofficiency user retains limitations after switching.
8. Tenant feature override does not affect another tenant.
9. Reports and every aggregate contain only event tenant.
10. Cofficiency actor activity appears in the selected customer tenant.
11. Historical seeded logs remain AdvantageFirst.
12. Global docs, release notes, roles, and navigation layout remain global.
13. Inactive tenants cannot be selected or receive new data.
14. Cofficiency tenant cannot be archived/renamed.
15. Remembered inactive tenant safely falls back to Cofficiency.

Run the full suite and report exact commands/results.

---

## Documentation

Update:

- `docs/ARCHITECTURE.md` with home versus active tenant, model ownership, authorization pattern, and skunkBOX interim boundary.
- `docs/USER_MANUAL.md` with tenant switcher, tenant administration, user creation semantics, feature overrides, and reporting attribution.
- Any quick-start/setup documentation that must mention seeded Cofficiency/AdvantageFirst tenants or migrations.

Include explicit future requirements:

- Calls must be tenant-owned when implemented.
- Components / AI Assets require tenant-aware skunkBOX management APIs.
- Future skunkBOX requests will carry tenant ID in addition to tenant-specific configuration.

---

## Final acceptance

Before declaring complete:

- Upgrade a disposable copy of a pre-tenant database and verify migration counts/ownership.
- Exercise switching between Cofficiency, AdvantageFirst, and a second customer tenant.
- Confirm no page leaks another tenant's names/counts in HTML, dropdowns, errors, or JSON.
- Confirm global documentation and release notes remain accessible.
- Confirm all PRD security and functional acceptance criteria.

---

## Deliverables

- Fully tenant-filtered Reporting
- Complete event-time logging attribution
- Repository-wide isolation audit document
- Adversarial regression suite
- Updated architecture/user/setup documentation
- Final checklist mapping implementation to every PRD acceptance criterion

Do not implement Calls, Components / AI Assets, billing, tenant branding, tenant-specific roles, or skunkBOX tenant-ID contracts in this phase.
