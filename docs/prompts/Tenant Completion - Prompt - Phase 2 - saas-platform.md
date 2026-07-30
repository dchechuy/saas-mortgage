# Phase 2 — skunkBOX Residual Ownership and Service-Boundary Hardening

**Target system:** `saas-platform`  
**Product name:** skunkBOX  
**System role:** Cofficiency administrative/backend platform and authoritative tenant/AI-asset store

Do not implement this phase in `saas-mortgage` (the Client Portal).

Read the cross-system PRD, Phase 1 completion, `docs/TENANT_ISOLATION_AUDIT.md`, MCP server code, background jobs, Persona defaults, Red Team, Ad Hoc, and document upload models/routes.

---

## Goal

Resolve or explicitly codify the remaining skunkBOX ownership and trust-boundary findings:

- Persona default flags are global singletons.
- `RedTeamRun` and `AdHocRequest` have unclear tenant ownership.
- `DocumentUploadJob` may lack tenant attribution.
- MCP `/tools/call` relies only on network isolation.
- The prior audit did not perform a complete line-by-line review of every admin module.

---

## Product-safe defaults

Use these defaults unless current code proves a different explicit product requirement:

- Persona defaults are per tenant, while Shared Cofficiency Personas may be eligible fallbacks.
- Red Team runs/results are tenant-owned when targeting a tenant-owned or Shared Persona.
- Ad Hoc requests inherit tenant from their Component/Persona and store it directly for history.
- Every Document upload job stores a required tenant, including jobs without a selected collection.
- MCP tool execution requires application authentication in addition to network isolation.

Do not tenant-scope genuinely global infrastructure such as Azure model configuration or global taxonomies without a documented product decision.

---

## Persona defaults

Replace global `is_default*` singleton behavior with tenant-aware defaults:

- Defaults are unique per `(tenant_id, use_case/default_type)`.
- Bulk clearing includes tenant predicate.
- A Shared Cofficiency Persona may be selected as a tenant fallback without changing ownership.
- Every consumer resolves defaults using tenant visibility.

Add migration/backfill rules that preserve current effective behavior for Cofficiency.

---

## Red Team and Ad Hoc

Add explicit event/root tenant ownership:

- A run/request receives tenant from the selected target.
- Cross-tenant target combinations are rejected.
- Results, transcripts, exports, filters, and background jobs inherit/revalidate tenant.
- Shared Persona use attributes the run to the consuming tenant, not Cofficiency.
- Internal cross-tenant support access follows Phase 1 permissions.

If either surface is intentionally kept Cofficiency-only, encode that restriction server-side and document it rather than leaving ownership ambiguous.

---

## Document upload jobs

Add required `tenant_id` to `DocumentUploadJob`.

- Derive it from trusted admin context or target collection.
- Validate target collection tenant when provided.
- Store tenant before starting background work.
- Revalidate tenant at worker execution.
- Scope job status, errors, downloads, retries, and cleanup.
- Backfill existing jobs to Cofficiency unless a reliable collection relationship provides a different owner.

---

## MCP authentication

Add authenticated calls from skunkBOX application workers to MCP `/tools/call`:

- Dedicated secret or signed request
- Rotation-friendly configuration
- Constant-time secret validation
- Replay protection when practical
- No secret in logs/errors
- Fail closed

Preserve trusted server injection of `tenant_id`; caller/LLM tool arguments must never override it.

Document the remaining network-layer assumptions.

---

## Complete audit

Perform the line-by-line tenant review deferred by the prior audit for:

- Components
- Datasets
- Experiments
- AI functions
- Skills
- Red Team
- Models/configuration
- Users/roles
- Categories/taxonomies
- MCP administration
- Persistent documents/files
- RAG and Agent execution

Classify every query as tenant-owned, inherited, Shared-visible, or intentionally global. Fix unexplained broad queries.

---

## Tests and baseline

- Add migration and adversarial coverage for every item above.
- Run focused tenant tests and the full suite.
- Also repair the two currently failing evaluation baseline tests concerning null/empty enum actual values, or update the implementation/tests according to the intended scoring rule after documenting the decision.
- Do not declare complete with a red full-suite baseline.

Update architecture, audit, operations documentation, and `CHANGELOG.md`.

