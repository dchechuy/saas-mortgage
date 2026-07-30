# Phase 4 — skunkBOX Customer Agent Configuration API

**Target system:** `saas-platform`  
**Product name:** skunkBOX  
**System role:** Authoritative backend for AI Agents, knowledge collections, Components, Datasets, and Experiments

This phase adds backend APIs needed by the Client Portal. Do not build the customer UI here; that belongs to Phase 5 in `saas-mortgage`.

Read the management API contract, Persona/collection tenancy implementation, Shared rules, service-credential authentication, and existing Persona domain services.

---

## Goal

Allow the Client Portal to create and edit tenant-owned AI Agents and configure their knowledge collections while preserving read-only Shared Cofficiency Agents.

Today skunkBOX can represent:

- Tenant Agent using tenant-private and Shared Cofficiency collections
- Shared Cofficiency Agent visible to all tenants

But the Client Portal does not yet have a complete management API/UI for configuring those associations.

---

## Management API

Extend `/api/v1/management/agents` with:

- List/get existing behavior
- Create tenant Agent
- Update allowed Agent fields
- Archive/reactivate
- List eligible collections
- Replace or patch collection associations
- Return dependency/validation information
- Optional clone Shared Agent into a private tenant Agent only if explicitly supported; otherwise keep out of scope

Use the existing Cophy service credential with `asset_management`.

---

## Rules

- Tenant UUID comes from authenticated management request context.
- Created Agent is owned by that tenant.
- Customer requests cannot set `is_shared`.
- Shared Agent is read/use only and cannot be mutated.
- Tenant Agent may reference:
  - Collections owned by the tenant
  - Shared Cofficiency collections
- Tenant Agent may not reference another tenant's private collection.
- Shared Cofficiency Agent dependency rules remain unchanged.
- Filters/counts/direct IDs return safe denial across tenants.
- Archive, never hard-delete.
- Mutations are idempotent where retries could duplicate associations.

Refactor web-route business logic into services reused by admin UI and API rather than duplicating Persona state rules.

---

## Response contract

Return enough data for Cophy:

- Stable Agent identifier
- Name/description/status
- Owner and `is_shared`
- `can_edit`
- Selected collections
- Eligible collection choices with owner/Shared labels
- Validation errors
- Version/update timestamp for optimistic conflict detection if supported

Update the management API contract.

---

## Tests

Cover:

- Tenant Agent create/edit/archive
- Own + Shared collection association
- Cross-tenant collection rejection
- Shared Agent mutation rejection
- Customer cannot publish Shared
- Forged tenant/resource IDs
- Service capability/revocation
- Idempotent association update
- Admin UI still uses the same domain rules

Run the full suite and update `CHANGELOG.md`.

