# Phase 2 — skunkBOX Knowledge and Shared AI Agents

You are working on `saas-platform` (skunkBOX).

Read the cross-system PRD, completed Phase 1, repository instructions, and all routes/services/models for documents, collections, Personas, RAG, chat, API access, skills, attachments, and background processing.

Implement only Phase 2.

---

## Goal

Tenant-isolate knowledge collections/documents and AI Agents (Personas), while allowing Cofficiency to publish read-only Shared collections and Shared Agents to every active tenant.

---

## Ownership and sharing

Add required `tenant_id` and `is_shared=false` to:

- `DocumentCollection`
- `Persona`

Add required ownership to `Document` and enforce:

- A Document has exactly one owning collection.
- Document and collection tenant match.
- Sharing is inherited from the collection.
- Only Cofficiency-owned collections/Personas may be Shared.

All existing rows remain Cofficiency-owned and private after migration. Provide an explicit Cofficiency-admin action to mark reviewed collections/Personas Shared. Do not automatically share every collection.

If current `DocumentCollectionMember` data allows multiple memberships:

- Add a pre-migration audit.
- Fail with a report if any Document has more than one collection unless an explicit reviewed mapping is provided.
- Do not silently choose a collection.
- Migrate toward one authoritative membership representation and update dependent code consistently.

---

## Visibility helpers

Create centralized, tested predicates/helpers:

- Owned: `resource.tenant_id == tenant.id`
- Visible: owned OR Cofficiency-owned Shared
- Mutable: owned only, with ordinary permissions

Do not grant mutation rights to another tenant merely because a resource is visible.

Use the helpers in lists, counts, filters, direct lookups, search, RAG, downloads, upload jobs, reprocessing, collection membership, and API allowlist checks.

---

## Collection and document behavior

- Tenant users/admin context sees tenant collections plus Shared Cofficiency collections.
- Shared rows are visibly labeled and read-only outside Cofficiency.
- Customer-owned collections/documents are never visible to other tenants.
- A tenant collection cannot contain a Cofficiency shared Document because the Document remains in its one Cofficiency collection.
- Agents may attach multiple collections, enabling private + Shared RAG.
- Tenant API keys can access only owned or Shared collections, further narrowed by existing collection allowlists.
- Search results, counts, citations, file downloads, and chunk retrieval must not leak private records.

Audit embeddings/vector metadata: every search path must constrain candidate documents by effective visibility even if the vector store itself is not tenant-partitioned.

---

## Persona / AI Agent behavior

- Tenant Agent: owned/mutable/useable by one tenant.
- Shared Agent: Cofficiency-owned, read-only/useable by every active tenant.
- Only Cofficiency can share/unshare.
- Tenant Agent dependencies may include own resources plus Shared Cofficiency resources.
- Shared Agent dependencies must all be Cofficiency-owned and Shared/global-safe.
- Validate dependencies on create/update/share and before execution.
- Unsharing a collection used by a Shared Agent is blocked until dependencies are resolved.
- A customer using a Shared Agent creates tenant-owned conversations, sessions, attachments, and logs.

Update all Persona direct-ID/list/filter/chat/API routes. Existing key/persona allowlists may restrict visible Agents but never expand visibility.

---

## Administrative UI

In skunkBOX:

- Add Shared checkbox/control to Cofficiency collection and Agent administration.
- Hide or disable Shared for non-Cofficiency context.
- Label ownership and Shared status.
- Confirm potentially disruptive unsharing and show dependencies.
- Never imply shared ownership.

---

## Tests

Use Cofficiency plus two customer tenants. Cover:

- Existing data is Cofficiency/private
- Only Cofficiency can publish Shared
- Both customers read/use Shared collections/Agents
- Customers cannot mutate Shared records
- Private resources never cross tenants
- One Document/one collection invariant
- Same-tenant owner invariant
- Tenant Agent can combine own and Shared collections
- Shared Agent cannot reference private collection/skill/dependency
- Unsharing dependency protection
- RAG/search/download/API filters
- Customer use of Shared Agent produces customer-owned operational records
- Forged IDs return safe denial

Run the full suite and update `CHANGELOG.md`.

---

## Deliverables

- Knowledge/Persona ownership migrations
- Sharing and visibility service
- Tenant-safe routes, RAG, APIs, workers, and UI
- Cardinality migration audit
- Security/regression tests

