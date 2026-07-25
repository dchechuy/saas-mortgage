# Phase 4 — skunkBOX Provisioning and Customer Management APIs

You are working on `saas-platform` (skunkBOX).

Read the cross-system PRD, completed Phases 1–3, API conventions/authentication, and repository instructions.

Implement only Phase 4.

---

## Goal

Expose secure service-to-service APIs for authoritative tenant synchronization and Cophy customer management of Components, versions, datasets, experiments, results, knowledge collections, and AI Agents.

---

## Service authentication

Introduce a dedicated Cophy service credential/capability separate from ordinary tenant API keys.

- Store secrets encrypted/hashed according to existing conventions.
- Support key rotation and active/revoked state.
- Define explicit capabilities such as tenant provisioning and asset management.
- Require a validated active tenant UUID for tenant-scoped management calls.
- Never trust UUID alone.
- Log credential, tenant, endpoint, operation, target, status, and latency.
- Apply rate/size limits where existing infrastructure supports them.

Ordinary `SkunkApiKey` continues to resolve exactly one tenant and cannot invoke provisioning APIs.

---

## Tenant lifecycle API

Implement the PRD endpoints for list/get/create/update/archive/reactivate.

- Mutation requires provisioning capability.
- Use UUID public identifiers.
- Create supports idempotency.
- Protected Cofficiency constraints apply.
- Responses are stable and sufficient for Cophy mirror upsert.
- Pagination or updated-since synchronization is supported.
- Archived tenant remains queryable for reconciliation/history but unavailable for new customer operations.

---

## Customer management API

Add versioned endpoints for:

- Components: list/get/create/update/archive/reactivate
- Fields/prompts/schemas/instructions
- Versions: list/create/update where allowed
- Promote release/production
- Datasets: list/get/create/update/import/archive
- Experiments: create/run/status/results/metrics
- Knowledge collections: list owned + Shared; get
- AI Agents: list owned + Shared; get

Expose mutation APIs for tenant-owned collections/Agents only if Cophy currently needs them; otherwise document/read APIs without speculative UI.

Reuse existing domain services. Do not duplicate complex route logic or call web routes internally. Refactor business operations into shared service functions used by both skunkBOX UI and API.

---

## Visibility and mutation

- List/read returns owned resources plus Shared resources only for knowledge/Agents.
- Components/datasets/experiments are owned-only.
- Mutations require owned resources.
- Shared resources return explicit `is_shared`, `owner`, and `can_edit=false`.
- Foreign IDs are reloaded and validated in tenant context.
- Filters, counts, pagination, exports, and results apply identical predicates.
- Cross-tenant and unauthorized targets return safe 404/403 without disclosure.
- Costly create/run/promote actions support idempotency where retries could duplicate state.

Define consistent error envelopes and public resource IDs. Do not expose local database IDs if avoidable.

---

## API contract documentation

Write an API contract document with:

- Authentication headers
- Tenant context
- Capability requirements
- Request/response examples
- Pagination/filtering
- Shared-resource semantics
- Idempotency
- Error codes
- Versioning/compatibility policy

This document is the contract used by Phases 5–7 in Cophy.

---

## Tests

Cover:

- Service credential capabilities/revocation
- Ordinary key cannot provision/manage
- Tenant UUID mismatch/inactive handling
- Idempotent tenant creation and costly operations
- Owned/Shared list visibility
- Shared mutation rejection
- Every cross-tenant identifier class
- Same-tenant relationship validation
- Pagination/count isolation
- Dataset/experiment job context
- Audit logging
- API contract examples via integration tests

Run full tests and update `CHANGELOG.md`.

---

## Deliverables

- Service authentication/capabilities
- Tenant provisioning API
- Customer asset/quality management API
- Shared domain services
- Contract documentation
- Integration/security tests

