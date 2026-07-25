# PRD: Cross-System Tenants and Customer AI Assets

**Feature:** Authoritative skunkBOX tenants, shared knowledge assets/agents, and customer AI Asset management  
**Systems affected:** `saas-platform` (skunkBOX) and `saas-mortgage` (Cophy Portal)  
**Date:** 2026-07-25  
**Status:** Approved for phased implementation

---

## 1. Context

skunkBOX is the Cofficiency administrative/backend platform. Cophy Portal is the customer-facing portal. Cophy already implements local tenant isolation for users, configuration, conversations, reporting, and feature flags.

Customer-facing features will now expose skunkBOX resources:

- Components / AI Assets
- Component fields, schemas, instructions, and prompts
- Component versions
- Datasets
- Experiments and evaluations
- AI quality results
- AI Agents
- Knowledge-base documents and collections

skunkBOX currently does not have a tenant boundary. Relying only on Cophy to filter resources would be unsafe because skunkBOX stores and executes the assets. skunkBOX must independently own tenant identity and enforce tenant access in its database, administrative UI, and APIs.

---

## 2. Goals

1. Make skunkBOX the authoritative tenant registry.
2. Keep Cophy's local tenant table as a synchronized mirror for login, user assignment, switching, reporting, and availability.
3. Use one stable cross-system tenant UUID instead of exchanging local integer IDs.
4. Assign every tenant-owned skunkBOX record to exactly one owning tenant.
5. Keep Components and their quality-management resources private to one tenant.
6. Let Cofficiency publish knowledge-base collections and AI Agents for read-only use by every tenant.
7. Let customers fully manage their own Component lifecycle and AI quality workflows through Cophy APIs/UI.
8. Enforce tenant ownership in skunkBOX even when Cophy sends a forged or buggy request.

---

## 3. Non-Goals

- Multi-owner Components.
- Sharing Components between tenants.
- Sharing knowledge assets with only an arbitrary subset of tenants.
- Industry-specific sharing in v1; Cofficiency “Shared” means every active tenant.
- Customer editing of shared Cofficiency records.
- Direct browser access to privileged skunkBOX APIs.
- Replacing Cophy's local tenant/user model.
- Tenant-specific roles in either system.
- Hard deletion of tenants or Components.
- Copy-on-write customization of shared Agents in v1.

---

## 4. Confirmed Decisions

| Area | Decision |
|---|---|
| Tenant authority | skunkBOX is authoritative. |
| Tenant administration | Cofficiency administrators manage tenants in tab 3 under skunkBOX **Users & Config**. |
| Cophy tenant data | Cophy keeps a local synchronized mirror and delegates lifecycle changes to skunkBOX. |
| Cross-system identity | A stable UUID identifies the same tenant in both databases. Local integer IDs are never exchanged. |
| Existing skunkBOX data | All existing skunkBOX records belong to Cofficiency. None migrate to AdvantageFirst. |
| Components | Exactly one owning tenant; never shared in v1. |
| Component versions/history | Inherit the Component's tenant and cannot cross it. |
| Customer Component rights | Create/edit fields, schemas, instructions/prompts; manage versions; promote release/production; manage datasets; run experiments/evaluations; review quality; archive, not hard-delete. |
| Knowledge documents | Exactly one owning tenant and exactly one collection in v1. |
| Knowledge collections | Exactly one owning tenant. Only a Cofficiency-owned collection may be marked Shared. |
| Shared knowledge | A shared Cofficiency collection and its documents are readable/useable by every active tenant. |
| AI Agents | Exactly one owning tenant. Only a Cofficiency-owned Agent may be marked Shared. |
| Shared Agents | Readable/useable by every active tenant; editable only by Cofficiency. |
| Customer Agents | Tenant Agents may use tenant-owned collections plus shared Cofficiency collections. |
| Shared Agent dependencies | A shared Cofficiency Agent may depend only on shared Cofficiency collections and other globally safe resources. |

---

## 5. Core Ownership Model

Every governed skunkBOX record has one owner:

```text
record.tenant_id -> tenant.id
```

Sharing does not create joint ownership. It grants read/use access to a Cofficiency-owned record:

```text
owner is Cofficiency AND is_shared = true
```

Effective resource access is:

```text
resource.tenant_id == caller_tenant.id
OR (
  resource.tenant_id == cofficiency.id
  AND resource.is_shared == true
)
```

Write access remains:

```text
resource.tenant_id == caller_tenant.id
```

Cofficiency administrators operating inside skunkBOX may manage Cofficiency resources and use the skunkBOX administrative tenant context according to existing permissions. External Cophy calls never receive broader Cofficiency administrative authority.

---

## 6. Authoritative Tenant Registry

### 6.1 skunkBOX `Tenant`

Add:

```python
class Tenant(db.Model):
    __tablename__ = "tenant"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_protected = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
```

Rules:

- `public_id` is an immutable UUID string.
- Cofficiency is seeded, protected, and cannot be archived, renamed, or re-slugged.
- AdvantageFirst exists as an active tenant even though existing skunkBOX assets remain Cofficiency-owned.
- Archived tenants cannot authenticate new API activity, receive new assets, or appear as selectable Cophy tenants.
- Tenant lifecycle mutations are idempotent and auditable.

### 6.2 Cophy `Tenant`

Add an immutable, globally unique `external_id` UUID holding skunkBOX `Tenant.public_id`.

- Existing Cofficiency and AdvantageFirst rows are mapped to the corresponding authoritative rows.
- Cophy local IDs remain unchanged.
- Tenant name, slug, and active state are synchronized fields.
- Cophy user foreign keys continue pointing to the local tenant row.
- A synchronization failure must not silently create an unrelated tenant with a different UUID.

---

## 7. Tenant Provisioning and Synchronization

skunkBOX exposes service-to-service tenant APIs authenticated with a dedicated Cophy service credential:

```text
GET    /api/v1/tenants
GET    /api/v1/tenants/<public_id>
POST   /api/v1/tenants
PATCH  /api/v1/tenants/<public_id>
POST   /api/v1/tenants/<public_id>/archive
POST   /api/v1/tenants/<public_id>/reactivate
```

Requirements:

- These endpoints are unavailable to ordinary tenant API keys.
- Mutations require Cofficiency administrative service capability.
- Creation supports an idempotency key.
- Responses include `public_id`, name, slug, active/protected state, and timestamps.
- Cophy create/archive/reactivate UI calls skunkBOX first, then upserts its mirror from the authoritative response.
- A periodic/manual reconciliation endpoint or command refreshes the complete mirror.
- If skunkBOX mutation succeeds but Cophy persistence fails, retry/reconciliation converges by `public_id`.
- Cophy cannot rename/archive protected Cofficiency.

---

## 8. API Tenant Authentication

Tenant context must be derived from authenticated server-side credentials, not trusted from arbitrary request input.

### Tenant API keys

Add required `tenant_id` to `SkunkApiKey`.

- A tenant API key is bound to exactly one tenant.
- `require_api_key` resolves `g.tenant` from the key.
- An optional tenant header/body value may be accepted only as a consistency assertion and must match the key's tenant.
- API logs store tenant at event time.
- Collection/persona/resource allowlists further restrict access; they never expand beyond the key's tenant/shared visibility.

### Cophy service credential

Use a separate service credential/capability for:

- Tenant provisioning/synchronization
- Customer Component/Dataset/Experiment management APIs
- Other explicitly authorized management operations

Each management request carries the active tenant UUID. skunkBOX validates:

1. Credential has the required capability.
2. Tenant UUID exists and is active.
3. Target resource is owned by that tenant, or is readable shared content when the operation is read/use.
4. Mutations never target shared Cofficiency content on behalf of a customer.

The browser never receives the skunkBOX service secret.

---

## 9. Components / AI Assets

### 9.1 Ownership

Add required tenant ownership to `Component`. All dependent records inherit through it unless an explicit tenant column materially improves audit/history:

- `ComponentVersion`
- `ComponentCommit`
- `ComponentChangeLog`
- Component skill relationships
- Optimizer sessions
- Experiments and experiment results tied to the Component
- Component-specific datasets and evaluation artifacts

Cross-tenant relationships are prohibited.

Components are never shared in v1. Two tenants may create similarly named Components; uniqueness for slugs/natural keys must be tenant-relative or use globally unique opaque identifiers without exposing another tenant.

### 9.2 Customer capabilities through Cophy

Customers with the relevant Cophy permission can:

- List and view tenant Components
- Create a Component
- Edit field definitions and input/output configuration
- Edit system instructions, prompts, schemas, formatting requirements, and policies
- Create/manage drafts and versions
- Promote versions to release and production
- View version and change history appropriate for customer use
- Create/import/manage datasets
- Run experiments/evaluations against eligible Component versions
- View results, quality metrics, errors, and comparisons
- Archive/reactivate Components

Customers cannot:

- Access another tenant's Component by ID/slug/filter
- Hard-delete Components
- Use skunkBOX-only system administration
- Use optimizer or low-level internal audit tooling in the initial Cophy exposure unless separately approved

Cophy is a thin customer UI over skunkBOX domain APIs; it does not reimplement versioning/evaluation business rules locally.

---

## 10. Knowledge Base

### 10.1 Collection ownership and sharing

Add to `DocumentCollection`:

- required `tenant_id`
- `is_shared` default false

Rules:

- Tenant collection: owned/read/write by that tenant.
- Shared collection: owner must be Cofficiency and `is_shared=true`.
- Shared collections are read-only/useable by every active tenant.
- Customer tenants cannot set `is_shared`.
- Unsharing a collection requires dependency checks and an explicit administrative confirmation.

### 10.2 Document ownership and membership

Each Document:

- Has exactly one required `tenant_id`.
- Belongs to exactly one collection in v1.
- Must have the same owner tenant as its collection.
- Inherits effective sharing from its collection; a separate document-level Shared checkbox is unnecessary and could create contradictory state.

Although the current schema may support multiple collection memberships, this release establishes a single owning collection. Migration must detect multiple memberships and stop with a clear report or resolve them through an explicitly reviewed mapping—never silently choose.

All document versions, chunks, embeddings, uploads, metadata, searches, and download paths inherit/enforce the Document/Collection visibility boundary.

### 10.3 Usage

- Tenant users can list/search/use their tenant's collections plus shared Cofficiency collections.
- Tenant users cannot edit/delete/reprocess shared documents.
- A tenant collection cannot directly contain a shared Cofficiency document because a document has exactly one collection.
- Agents may attach multiple collections, allowing a tenant Agent to combine a tenant-private collection with one or more shared Cofficiency collections.

Existing skunkBOX documents and collections migrate to Cofficiency. Existing public mortgage collections are marked Shared only after migration validation; the migration/prompt must not assume every arbitrary collection is safe without an explicit reviewed allowlist or a post-migration admin action.

---

## 11. AI Agents

In skunkBOX, the existing Persona concept is the AI Agent domain record.

Add to `Persona`:

- required `tenant_id`
- `is_shared` default false

Rules:

- Tenant Agent: owned/editable/useable by one tenant.
- Shared Agent: Cofficiency-owned, read-only/useable by every active tenant.
- Only Cofficiency may set or clear Shared.
- A tenant Agent may reference:
  - Tenant-owned collections
  - Shared Cofficiency collections
  - Tenant-owned skills/resources where applicable
  - Explicitly shared Cofficiency dependencies
- A shared Agent may reference only shared Cofficiency collections and dependencies safe for all tenants.
- Changing/unsharing dependencies must validate existing shared Agent references.
- Customer use of a shared Agent creates tenant-owned conversations/sessions/logs; it does not change Agent ownership.

Existing Personas migrate to Cofficiency and private by default. Cofficiency explicitly marks safe Agents Shared.

---

## 12. Datasets, Experiments, and Quality Measurement

Quality resources must not become a cross-tenant side channel.

- Dataset ownership is required and private to one tenant.
- Dataset rows/files/labels inherit Dataset ownership.
- Experiment ownership is required and must match Component and Dataset.
- Experiment results, evaluation results, reviews, events, optimizer sessions, and generated artifacts inherit owning Experiment/Component tenant.
- A customer can run an experiment only when Component, version, and Dataset resolve to the same active tenant.
- Shared knowledge/Agents do not make private Component datasets or results shared.
- Aggregates, comparisons, reporting, exports, and background workers filter/enforce tenant.
- Worker job payloads include immutable tenant context and revalidate it on execution.

---

## 13. Administrative UI

### skunkBOX

Add **Tenants** as tab 3 under **Users & Config**, shifting later tabs as needed.

The tab provides:

- Tenant list
- Create
- Edit safe metadata
- Archive/reactivate
- Protected indicator
- Stable UUID display/copy for troubleshooting
- Counts of owned Components, collections, Agents, and API keys
- Reconciliation/status information where useful

skunkBOX internal users remain Cofficiency administrative users in v1. Tenant selection in this UI is an administrative data context, not user membership.

### Cophy

- Keep the existing tenant switcher and local tenant mirror.
- Replace purely local tenant lifecycle operations with skunkBOX provisioning API calls.
- Show synchronization failures clearly.
- Do not let ordinary customer users administer tenants.
- Continue using local tenant IDs for local records and the stable UUID for skunkBOX requests.

---

## 14. Customer API Surface

Provide versioned skunkBOX management APIs sufficient for Cophy UI. Exact resource shapes must be documented with OpenAPI-style request/response examples.

Minimum groups:

```text
/api/v1/management/components
/api/v1/management/components/<id>
/api/v1/management/components/<id>/versions
/api/v1/management/components/<id>/promote
/api/v1/management/datasets
/api/v1/management/datasets/<id>
/api/v1/management/experiments
/api/v1/management/experiments/<id>
/api/v1/management/experiments/<id>/results
/api/v1/management/knowledge/collections
/api/v1/management/agents
```

API rules:

- Tenant context comes from authorized Cophy service request plus validated tenant UUID.
- Opaque/public resource identifiers are preferred across systems.
- List endpoints return owned records plus shared records only where relevant.
- Mutation endpoints accept owned records only.
- Errors do not disclose cross-tenant existence.
- Pagination, filters, counts, and exports apply the same tenant visibility predicate.
- Create/update payloads never accept an ownership tenant that differs from authenticated context.
- Idempotency is used for costly or retry-prone mutations.

---

## 15. Migration

### skunkBOX

1. Create Cofficiency and AdvantageFirst authoritative tenants with stable UUIDs.
2. Add tenant ownership columns nullable.
3. Assign all existing records to Cofficiency.
4. Bind existing API keys to Cofficiency unless an explicit reviewed mapping says otherwise.
5. Add `is_shared=false` to collections and Personas.
6. Detect document collection membership cardinality.
7. Require explicit review before marking existing public knowledge collections Shared.
8. Add tenant-relative constraints and same-tenant relationship validation.
9. Make required ownership non-null.
10. Preserve record counts/history.

No existing Component, Persona, document, collection, conversation, log, dataset, or experiment is assigned to AdvantageFirst.

### Cophy

1. Add `Tenant.external_id`.
2. Map local Cofficiency and AdvantageFirst to authoritative UUIDs.
3. Require non-null unique mapping after reconciliation.
4. Keep all existing local tenant ownership unchanged.
5. Convert tenant lifecycle UI to authoritative API-backed behavior.

---

## 16. Security Requirements

1. skunkBOX independently enforces tenant access.
2. A Cophy tenant UUID alone is not authentication.
3. A tenant API key cannot assert another tenant.
4. A management service request cannot mutate shared Cofficiency resources for a customer.
5. Cross-tenant IDs/slugs/filters return 404 or safe denial.
6. Same-tenant validation applies to every relationship and worker job.
7. Shared collections/Agents are read/use only outside Cofficiency.
8. Only Cofficiency can publish/unpublish shared resources.
9. Unsharing validates dependencies and active use.
10. API logs record credential, actor when known, tenant, operation, target, and outcome.
11. Tenant archival blocks new API operations without erasing history.
12. Cophy local mirror drift cannot grant access in skunkBOX.

---

## 17. Acceptance Criteria

1. skunkBOX Tenants tab is third under Users & Config.
2. skunkBOX is authoritative and Cophy mirrors tenants by UUID.
3. Existing skunkBOX data remains Cofficiency-owned.
4. AdvantageFirst exists but receives no legacy skunkBOX assets automatically.
5. Customer A cannot see/use Customer B private resources.
6. Customer tenants can see/use Shared Cofficiency collections and Agents.
7. Customers cannot mutate shared resources.
8. A document has one owner and one collection.
9. A tenant Agent can combine tenant-private and Shared collections.
10. A Shared Agent cannot reference private resources.
11. Components and all versions/quality resources remain single-tenant.
12. Customers can complete the agreed Component/version/dataset/experiment workflow in Cophy.
13. Background jobs and reports remain tenant-isolated.
14. Tenant lifecycle changes converge between skunkBOX and Cophy.
15. Forged cross-tenant API requests fail inside skunkBOX.

---

## 18. Phased Delivery

### Phase 1 — skunkBOX tenant registry and migration

Add authoritative Tenant, stable UUIDs, Users & Config tab 3, API-key/log ownership foundation, and migrate all existing data to Cofficiency.

### Phase 2 — skunkBOX knowledge and Agent sharing

Tenant-scope collections/documents/Personas, enforce one collection per document, implement Cofficiency Shared collections/Agents, validate dependencies, and secure existing use paths.

### Phase 3 — skunkBOX Components and quality tenancy

Tenant-scope Components, versions, datasets, experiments, evaluations, workers, histories, and all dependent queries/relationships.

### Phase 4 — skunkBOX provisioning and customer management APIs

Add service authentication, tenant lifecycle/sync endpoints, and tenant-safe Component/version/dataset/experiment/knowledge/Agent APIs.

### Phase 5 — Cophy authoritative tenant synchronization

Add external UUID mapping, convert tenant lifecycle UI to skunkBOX-backed operations, add reconciliation, and propagate trusted active tenant UUID.

### Phase 6 — Cophy shared knowledge and Agent integration

Expose owned plus Shared knowledge/Agents with read-only distinctions and tenant-safe proxy/use behavior.

### Phase 7 — Cophy Components and quality management

Build customer Component/version/dataset/experiment/results UI over skunkBOX management APIs.

### Phase 8 — Cross-system audit and rollout

Run migration reconciliation, adversarial security testing, job/report audits, operational documentation, and staged enablement.

---

## 19. Future Extensions

- Selective sharing to named tenants.
- Shared Component templates with explicit clone/fork lineage.
- Customer customization of shared Agents through derived tenant Agents.
- Industry-scoped shared libraries.
- Event/webhook synchronization replacing or supplementing polling.
- Common identity/authorization service if more customer portals are introduced.

