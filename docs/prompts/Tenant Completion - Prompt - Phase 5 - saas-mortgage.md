# Phase 5 — Client Portal Agent and Knowledge Configuration

**Target system:** `saas-mortgage`  
**Product name:** Cophy Portal / Client Portal  
**System role:** Customer-facing tenant UI

This phase consumes the skunkBOX API completed in Phase 4. Do not duplicate authoritative Agent/knowledge rules locally.

Read the management API contract, existing local `AiAgent` mirror behavior, `app/skunkbox_client.py`, System Config Agent UI, Learning Center, permissions, and feature flags.

---

## Goal

Let authorized customer users manage tenant-owned AI Agents and configure each Agent with tenant-private and Shared Cofficiency knowledge collections.

Shared Cofficiency Agents remain read-only.

---

## UI behavior

Under the appropriate Client Portal Agent configuration surface:

- List tenant-owned Agents plus Shared Cofficiency Agents.
- Clearly label owner, Shared status, and editability.
- Create a tenant Agent.
- Edit Agent name, description, prompts/instructions, and other approved fields.
- Select multiple eligible collections:
  - Tenant-owned collections
  - Shared Cofficiency collections
- Archive/reactivate tenant Agents.
- Show Shared Agent configuration read-only.
- Do not expose a Shared checkbox to customer tenants.
- Do not expose hard deletion.

Use existing global role templates, active-tenant permissions, and tenant feature flags.

---

## Local model strategy

skunkBOX remains authoritative.

Review the existing local `AiAgent` rows:

- Tenant-owned hand-configured rows
- Per-tenant mirrors of Shared skunkBOX Agents

Choose and document one consistent strategy:

1. Convert all Agent records to synchronized pointers to authoritative skunkBOX Personas, or
2. Retain the current mixed model with explicit ownership/type markers and reliable reconciliation.

Do not create duplicate local rows or silently repurpose a Shared mirror into a tenant-owned Agent.

Every local pointer uses a stable skunkBOX identifier and the local active tenant.

---

## Client and security

- Add centralized skunkBOX client calls for Agent mutations/collection associations.
- Derive tenant UUID only from server-side active tenant.
- Treat all Agent/collection IDs as untrusted.
- Preserve safe 404/403 behavior.
- Add CSRF tokens per Phase 3.
- Use idempotency keys for create/association mutations.
- Record Client Portal activity under active tenant.
- Add a local management-call audit/correlation record as described below.

---

## Cophy-side management API observability

Backfill the partial audit requirement for `skunkbox_client.py`:

- Add a local log record or extend `ApiRequestLog` for management calls.
- Store active tenant, endpoint/operation, target identifier, status, latency, and a skunkBOX correlation/request ID when returned.
- Never store service secrets or sensitive bodies.
- Logging failure must not hide the customer operation in production but must fail visibly in tests.

Apply this consistently to tenant lifecycle, Components, Datasets, Experiments, knowledge, and Agent management calls—not only this new screen.

---

## Tests

Cover:

- Customer Agent creation
- Own + Shared collection selection
- Cross-tenant collection/Agent rejection
- Shared Agent read-only behavior
- Tenant switching invalidates open edit URLs
- Local mirror/pointer conflict handling
- Backend timeout and partial success
- CSRF and permission checks
- Activity attribution and local management-call audit logging
- No secret exposure

Run the complete suite and update user manual, architecture, operations runbook, and tenant audit.

