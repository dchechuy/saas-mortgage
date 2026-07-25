# Phase 3 — skunkBOX Components and Quality Tenancy

You are working on `saas-platform` (skunkBOX).

Read the cross-system PRD, completed Phases 1–2, repository instructions, and all Component/version/dataset/experiment/evaluation/optimizer/worker code.

Implement only Phase 3.

---

## Goal

Make Components and the complete quality-management graph private to exactly one tenant, including asynchronous processing and reporting.

Components are never Shared in v1.

---

## Ownership graph

Add required `tenant_id` to the root records where it preserves immutable ownership and efficient auditing:

- `Component`
- Dataset root models
- `Experiment`
- Long-lived jobs/logs whose tenant cannot be safely inferred later

Dependent records inherit and must match the root:

- Component versions
- Commits/change logs
- Component-skill associations
- Optimizer sessions/proposals/regression results
- Dataset rows/files/labels/lineage
- Experiment results/events/evaluations/reviews/corrections
- Generated artifacts and exports

Inventory the real model graph before migrating. Document each model as direct-owned, inherited-owned, or global. Do not add redundant columns without a reason, but never leave an authorization path ambiguous.

All existing rows migrate to Cofficiency.

---

## Component behavior

Apply tenant context to:

- Lists, tab counts, filters, dashboard counts
- Create/view/edit/archive/reactivate
- Slug/name uniqueness
- Draft/version creation
- Release/production promotion
- Commits, diffs, reverts, change logs
- Skills/dependency selection
- Optimizer flows
- Internal import/MCP tools
- Ad hoc execution and selectable versions
- Exports and generated definitions

Cross-tenant IDs must fail before related information is loaded. Bulk version/status changes include tenant ownership.

---

## Datasets and experiments

- Dataset is owned by one tenant.
- Component/version and Dataset used by an Experiment must belong to the same tenant.
- Experiment and every result/event/review inherit that tenant.
- Customer tenant cannot compare against or copy private rows from another tenant.
- Filters, summaries, QMS metrics, exports, and reporting are tenant-scoped.
- Existing public/global taxonomy/configuration may remain global only after explicit classification.

---

## Workers

Every background job payload carries tenant public UUID or immutable local tenant ID plus root resource IDs.

At job start:

1. Resolve tenant.
2. Reject inactive tenant where appropriate.
3. Reload root resources.
4. Revalidate same-tenant ownership.
5. Write results/logs with event tenant.

Do not rely on Flask request context in threads/workers. Prevent a job queued for tenant A from writing tenant B results after data changes.

---

## Internal/admin tools

Update internal import and MCP tools:

- Tenant context is required for creation/mutation.
- Cofficiency admin defaults must be explicit, not silently global.
- Tool-created Components receive one tenant.
- Imports cannot reference another tenant's skills/assets.

Classify Categories, Skills, Azure models, prompts, and other configuration as tenant-owned or global. Record decisions in architecture documentation and enforce relationship rules accordingly.

---

## Tests

Cover:

- All legacy Component/quality data Cofficiency-owned
- Same titles/slugs according to chosen tenant-relative strategy
- Cross-tenant list/direct/bulk isolation
- Version/promotion/revert boundaries
- Same-tenant Component/Dataset/Experiment requirement
- QMS metrics and exports isolated
- Worker tenant propagation/revalidation
- Internal/MCP import requires tenant
- Cofficiency admin behavior explicit
- No Component sharing

Run the full suite and update `CHANGELOG.md`.

---

## Deliverables

- Ownership migration and model classification
- Tenant-safe Component/version lifecycle
- Tenant-safe datasets/experiments/evaluations/workers
- Audit of all direct and bulk access paths
- Regression tests and documentation

