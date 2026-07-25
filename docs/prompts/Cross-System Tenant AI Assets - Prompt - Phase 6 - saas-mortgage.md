# Phase 6 — Cophy Shared Knowledge and AI Agents

You are working on `saas-mortgage` (Cophy Portal).

Read the cross-system PRD, completed Phases 1–5, skunkBOX API contract, and existing Cophy Agent/Learning Center/conversation implementation.

Implement only Phase 6.

---

## Goal

Expose tenant-owned plus Shared Cofficiency knowledge collections and AI Agents through Cophy with correct read-only behavior and secure tenant propagation.

---

## API client

Extend the centralized skunkBOX client for:

- List/get visible knowledge collections
- List/get visible AI Agents
- Any approved tenant-owned collection/Agent mutation endpoints
- Existing RAG/chat/document operations under trusted active tenant UUID

Normalize errors and never expose service credentials or raw backend diagnostics to customers.

---

## Knowledge UX

In Learning Center/knowledge surfaces:

- Show active-tenant collections and Shared Cofficiency collections.
- Clearly label Shared and owner.
- Shared rows are read/use only.
- Do not show edit/delete/reprocess controls on Shared rows.
- Tenant-owned controls follow existing permissions.
- Documents appear through their single owning collection.
- Search/download/citation links proxy through Cophy and reauthorize active tenant on every request.

Do not locally duplicate authoritative document/collection records unless a deliberately minimal cache is required. If cached, treat skunkBOX authorization as authoritative.

---

## Agent UX

- Show active-tenant Agents plus Shared Cofficiency Agents.
- Label Shared and read-only.
- Tenant Agents may select own collections plus Shared collections.
- Shared Agents cannot be edited by customer tenants.
- Existing Cophy local `AiAgent` configuration must be reconciled with authoritative skunkBOX Persona identifiers and tenant UUIDs; do not create ambiguous duplicate ownership.
- If Cophy retains a local Agent mirror/config, add stable external identifiers and validate synchronization.

Using a Shared Agent creates a Cophy conversation owned by the active local tenant. Every skunkBOX call supplies that tenant's UUID even though Agent owner is Cofficiency.

---

## Security

- Browser cannot choose tenant UUID.
- Forged collection/Agent/document identifiers are rejected by both Cophy and skunkBOX.
- Switching tenants invalidates continued access to prior tenant private resources.
- Shared visibility never grants mutation.
- Existing Cophy permissions remain additive.
- Attachment and download routes use owning conversation plus active tenant.

---

## Tests

With Cofficiency and two customers:

- Both customers see/use Shared collection/Agent
- Each sees only own private resources otherwise
- Shared controls are read-only
- Forged mutation fails
- Tenant Agent may combine own + Shared collections
- Shared Agent conversation belongs to customer active tenant
- Switching invalidates old private URLs
- Search/download/citations remain isolated
- Backend/service errors are safe
- Existing docs/release notes remain global as before

Run the full suite.

---

## Deliverables

- Knowledge/Agent API client integration
- Shared/owned UI distinctions
- Stable backend identifiers/mirror updates where required
- Tenant-safe chat/RAG/proxy behavior
- Tests/documentation

