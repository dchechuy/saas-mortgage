# Phase 7 — Cophy Components and AI Quality Management

You are working on `saas-mortgage` (Cophy Portal).

Read the cross-system PRD, completed Phases 1–6, skunkBOX customer management API contract, and Cophy design/permission/navigation conventions.

Implement only Phase 7.

---

## Goal

Provide customer-facing management of tenant Components (AI Assets), versions, datasets, experiments, evaluations, and quality results without duplicating skunkBOX domain logic.

---

## Permissions and feature flags

Define Cophy page registry/navigation/permissions for:

- AI Assets / Components
- Datasets
- AI Quality / Experiments

Use tenant feature flags so Cofficiency can enable these incrementally per customer. Existing roles remain global templates and active-tenant isolation remains additive.

Decide whether one page permission or separate view/edit/run permissions best matches current conventions; document and seed safely.

---

## Component UX

Through the centralized service client, allow authorized customers to:

- List/search/filter active-tenant Components
- View Component fields/configuration
- Create
- Edit input/output fields, schemas, prompts, instructions, formatting, and policies
- View/manage drafts and versions
- Promote to release/production
- View customer-appropriate history
- Archive/reactivate

Do not expose hard deletion, cross-tenant copying, optimizer, or low-level internal audit tooling.

Show backend validation errors clearly without leaking another tenant's existence or secrets.

---

## Dataset UX

Allow:

- List/view/create/update/archive
- Define schema/columns as supported
- Upload/import within backend limits
- Preview rows and validation outcomes
- Associate only with active-tenant Components/versions

Files upload through Cophy server-side proxy or approved secure upload flow; never expose the service credential.

---

## Experiments and quality UX

Allow:

- Select active-tenant Component/version and Dataset
- Configure and start an experiment/evaluation
- Poll safe status endpoints
- View metrics, results, failures, comparisons, and reviews
- Navigate back to the exact Component/version/Dataset

Long-running jobs remain in skunkBOX. Cophy stores only minimal metadata needed for UI continuity, if any. Tenant switch must stop or reauthorize polling and prevent results from the previous tenant appearing.

---

## API and security behavior

- Active tenant UUID always comes from server-side context.
- Every resource ID is treated as untrusted.
- Cophy calls only documented skunkBOX domain APIs.
- Do not recreate version/promotion/evaluation state machines locally.
- CSRF and existing permission guards apply to mutations.
- Use idempotency keys for retry-prone create/run/promote actions.
- Lists, filter choices, counts, exports, and breadcrumbs remain tenant-safe.
- Log customer actions under active Cophy tenant and preserve skunkBOX audit IDs where returned.

---

## Tests

Cover the complete agreed customer workflow:

1. Create/edit Component fields and prompts.
2. Create draft/version and promote.
3. Create/import Dataset.
4. Run experiment.
5. View quality metrics/results.
6. Archive/reactivate Component.

Also cover:

- Permission and feature-flag denial
- Cross-tenant IDs in every mutation/read
- Switching during an open edit or job poll
- Idempotent retry
- Backend unavailable/timeout behavior
- No secret exposure
- No hard-delete/optimizer/internal controls
- Same-tenant Component/Dataset/Experiment selection

Run the full suite and perform a browser-level smoke test.

---

## Deliverables

- Navigation/permissions/feature flags
- Component/version UI
- Dataset UI
- Experiment/quality UI
- Centralized API client additions
- End-to-end and security tests
- User documentation

