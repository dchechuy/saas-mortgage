# PRD: Tenant Separation for Cophy Portal

**Feature:** Tenant-isolated workspaces for customer POCs and prototypes  
**Product:** Cophy.io / Cophy Portal / Client Portal  
**System affected:** `saas-mortgage` initially; `saas-platform` / skunkBOX later  
**Date:** 2026-07-24  
**Status:** Approved for phased implementation

---

## 1. Product Context

Cophy Portal is a playground for customer proofs of concept and prototypes. Multiple customer environments will share one application deployment, but customer data must not be visible or mutable across customer boundaries.

Cofficiency staff need to work across customer environments without receiving separate accounts. They must be able to select an active tenant and experience the portal as that tenant, while retaining their Cofficiency identity and existing role permissions.

---

## 2. Goals

1. Associate every user with exactly one immutable home tenant.
2. Isolate all tenant-owned assets, operational data, statistics, and reporting.
3. Let users whose home tenant is Cofficiency switch their active tenant workspace.
4. Remember the last tenant selected by each Cofficiency user.
5. Attribute activity to the tenant workspace in which it occurred, not merely to the actor's home tenant.
6. Preserve global documentation, release notes, role templates, and other explicitly global configuration.
7. Establish a safe foundation for future tenant propagation into skunkBOX APIs.

---

## 3. Non-Goals

- Users belonging to multiple home tenants.
- Reassigning a user to another tenant after creation.
- Tenant-specific roles or permission definitions in the initial release.
- Tenant-aware skunkBOX API contracts in the initial release.
- Building Components / AI Assets management before the skunkBOX management API exists.
- Implementing the future Calls feature.
- Custom tenant branding, domains, billing, quotas, or subscription management.
- Hard deletion of tenants.

---

## 4. Confirmed Product Decisions

| Decision | Requirement |
|---|---|
| User membership | Every user has exactly one home tenant. No membership join table in v1. |
| Internal identity | A user is internal when their home tenant is the protected Cofficiency tenant. No separate internal-user flag. |
| Tenant switching | Every Cofficiency user may select an active tenant. Existing roles and permissions still govern allowed actions. |
| External users | Users outside Cofficiency are permanently locked to their home tenant. |
| User reassignment | A user's home tenant cannot be changed after creation, including by Cofficiency administrators. |
| Tenant creation | Cofficiency administrators create and manage tenants. |
| User creation | A user created while tenant X is active is automatically assigned to tenant X. There is no tenant selector on the user form. |
| User visibility | The user list contains only users whose home tenant is the active tenant. Cofficiency itself shows only Cofficiency users. |
| Roles | Roles and permission definitions remain global, reusable templates. |
| Feature flags | All features are enabled by default. A tenant can override a feature to disabled (or back to enabled). |
| Historical migration | Existing business data and non-system users move to AdvantageFirst. The existing system `admin` user moves to Cofficiency. |
| Historical activity | All existing activity and request logs—including activity performed by the system admin—belong to AdvantageFirst. |
| New activity attribution | Activity is recorded against the active tenant at the time of the action. A Cofficiency actor working in another tenant produces activity for that selected tenant. |
| Cofficiency workspace | Cofficiency is a normal protected tenant for Cofficiency user management, but begins with no client operational assets. |
| skunkBOX | Isolation is initially indirect through tenant-specific integrations/API keys and AI agents. A tenant ID will be added to skunkBOX APIs later. |

---

## 5. Terminology

- **Home tenant:** The immutable tenant assigned to a user at creation.
- **Active tenant:** The tenant workspace currently being viewed and operated on.
- **Internal user:** A user whose home tenant is Cofficiency.
- **External user:** A user whose home tenant is any tenant other than Cofficiency.
- **Tenant-owned record:** A record carrying a required `tenant_id`, or a child record whose ownership is unambiguously inherited from such a parent.
- **Global record:** A record intentionally shared across tenants.

For an external user, home tenant and active tenant are always identical. For an internal user, the active tenant may be Cofficiency or any active customer tenant.

---

## 6. User Stories

### Tenant administration

**US-1.** As a Cofficiency administrator, I can create and edit a customer tenant.

**US-2.** As a Cofficiency administrator, I can archive a tenant so it can no longer be selected or used for new activity.

**US-3.** As any Cofficiency user, I can select an active tenant from a switcher immediately to the left of my user avatar.

**US-4.** As a Cofficiency user, I return to the last tenant I used when I sign in again.

### User administration

**US-5.** As an authorized user administrator, I see only users belonging to the active tenant.

**US-6.** As an authorized Cofficiency user working in a customer tenant, I can create a user who is automatically assigned to that customer tenant.

**US-7.** As an external tenant administrator, I can create and manage users only within my own tenant.

**US-8.** As any user administrator, I cannot change an existing user's home tenant.

### Operational isolation

**US-9.** As a tenant user, I see only my tenant's agents, conversations, knowledge-base content, integrations/API keys, models, attributes, dashboard statistics, and reports.

**US-10.** As a Cofficiency user, switching tenants changes all tenant-owned surfaces consistently.

**US-11.** As a tenant user, attempting to access another tenant's record by guessing or reusing its URL returns not found or forbidden without revealing the record.

### Feature flags and reporting

**US-12.** As an authorized administrator, I can disable a globally available feature for the active tenant.

**US-13.** As a reporting user, I see activity and API/LLM usage generated inside the active tenant, including actions performed there by Cofficiency users.

**US-14.** As a user, I see the same User Documentation and Release Notes regardless of tenant.

---

## 7. Tenant Governance Matrix

### 7.1 Tenant-scoped now

| Surface | Current implementation | Tenant behavior |
|---|---|---|
| Dashboard statistics | Counts users, roles, models, integrations, attributes, releases | Tenant-owned counts are filtered by active tenant. Global counts/content remain global and must be clearly treated as such. |
| Users | `User` | List/create/edit/toggle only within active tenant. Home tenant immutable. |
| LLM Models | `LlmModel` | Tenant-owned; names/default selection are unique within a tenant. |
| Attributes | `Attribute` | Tenant-owned; category/name uniqueness is per tenant. |
| Integrations and API keys | `Integration` | Tenant-owned; names are unique within a tenant. |
| AI Agents | `AiAgent` | Tenant-owned and may reference only an integration in the same tenant. |
| Conversations | `AgentConversation` plus child messages/attachments | Conversation stores tenant explicitly; messages and attachments inherit ownership. Agent and conversation tenant must match. |
| Knowledge base / Learning Center | Proxied through the selected agent/integration | Only tenant agents/integrations may be used; direct proxy routes enforce active tenant. |
| Feature Flags | `FeatureFlag` | Global flag catalogue/default plus per-tenant overrides. |
| Reporting | `UserActivityLog`, `LlmRequestLog`, `ApiRequestLog` | Logs store tenant at event time and reports filter by active tenant. |

### 7.2 Tenant-scoped later

| Surface | Future behavior |
|---|---|
| Calls | Every call record and query must carry/enforce tenant ownership when the feature is introduced. |
| Components / AI Assets | Components live in skunkBOX. The future management API must accept and enforce tenant ID; Cophy Portal must bind component requests to the active tenant. |
| skunkBOX tenant context | Cophy will eventually send tenant ID to skunkBOX APIs in addition to using tenant-specific credentials/configuration. |

### 7.3 Global

| Surface/model | Reason |
|---|---|
| User Documentation | Shared product documentation. |
| Release Notes / `ReleaseNote` | Shared product history. Activity produced while administering releases is still attributed to the active tenant where required by the activity policy. |
| Roles / `Role` / `Permission` | Global permission templates in v1. |
| Navigation layout / `NavSection` / `NavItem` | Global application structure. Tenant feature overrides determine whether flagged items appear. |
| Documentation prompts / `DocPrompt` | Global application configuration. |
| Feature flag catalogue / `FeatureFlag` | Defines available flags and their global default; tenant state lives in overrides. |

---

## 8. Data Model

### 8.1 New `Tenant`

```python
class Tenant(db.Model):
    __tablename__ = "tenant"

    id = db.Column(db.Integer, primary_key=True)
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

- Seed exactly one protected `cofficiency` tenant.
- Seed `advantagefirst` for migrated data.
- Protected tenants cannot be archived or renamed through normal UI.
- Archived tenants do not appear in the switcher and cannot receive new records.
- Tenant slugs are stable identifiers and are not user-editable after creation.

### 8.2 `User`

Add:

```python
tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
last_active_tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=True)
```

Rules:

- `tenant_id` is the immutable home tenant.
- For external users, `last_active_tenant_id` is ignored and active tenant always equals `tenant_id`.
- For Cofficiency users, `last_active_tenant_id` stores the most recently selected active tenant.
- If the remembered tenant becomes inactive, fall back to Cofficiency.
- Username and email remain globally unique because login identity is global.

### 8.3 Directly tenant-owned models

Add non-null `tenant_id` foreign keys to:

- `LlmModel`
- `Attribute`
- `Integration`
- `AiAgent`
- `AgentConversation`
- `LlmRequestLog`
- `UserActivityLog`
- `ApiRequestLog`

`AgentConversation.tenant_id` is intentionally stored even though it could be inferred. It preserves historical attribution and supports safe, direct authorization.

Children inherit tenant through their parent:

- `AgentMessage` → `AgentConversation`
- `MessageAttachment` → `AgentMessage` → `AgentConversation`

### 8.4 Tenant feature overrides

Keep `FeatureFlag` as the global catalogue and default state. Add:

```python
class TenantFeatureFlag(db.Model):
    __tablename__ = "tenant_feature_flag"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenant.id"), nullable=False)
    feature_flag_id = db.Column(db.Integer, db.ForeignKey("feature_flag.id"), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "feature_flag_id", name="uq_tenant_feature_flag"
        ),
    )
```

Effective state:

1. Use the active tenant override when present.
2. Otherwise use `FeatureFlag.is_enabled`.
3. Initial global defaults are enabled.

### 8.5 Uniqueness changes

Convert global business-data uniqueness to tenant-relative uniqueness:

- `LlmModel`: `(tenant_id, name)`
- `Attribute`: `(tenant_id, category, name)`
- `Integration`: `(tenant_id, name)`
- Any future tenant-owned natural key must include `tenant_id`.

---

## 9. Active Tenant Resolution

Create one central tenant-context service; routes must not independently invent tenant-selection logic.

Conceptual API:

```python
def is_cofficiency_user(user) -> bool: ...
def get_active_tenant(user=None) -> Tenant: ...
def get_active_tenant_id(user=None) -> int: ...
def require_tenant_record(record) -> None: ...
```

Resolution rules:

1. Unauthenticated requests have no active tenant.
2. External user → active tenant is always home tenant.
3. Cofficiency user → active tenant is `last_active_tenant_id` when active and valid.
4. Missing/invalid/inactive remembered tenant → Cofficiency.
5. Switching is accepted only for a Cofficiency user and an active target tenant.
6. A successful switch persists `last_active_tenant_id`.

The database-backed remembered tenant is the source of truth. Session state may cache it but cannot override authorization.

---

## 10. Authorization and Isolation Requirements

Tenant enforcement is additive to existing role/permission checks:

```text
authenticated
AND existing page/action permission
AND record.tenant_id == active_tenant.id
```

Required practices:

- Every tenant-owned list query begins with an active-tenant filter.
- Every create operation sets `tenant_id` from server-side active context, never from a client-supplied tenant field.
- Every read/update/toggle/archive/delete by ID verifies active-tenant ownership.
- Cross-tenant foreign keys are rejected (for example, an agent cannot use another tenant's integration).
- Bulk updates and deletes include tenant predicates.
- Filter dropdowns contain only active-tenant records.
- Tenant ID submitted by a browser is never trusted as authorization.
- Prefer a 404 for direct cross-tenant object access where revealing existence is unnecessary.
- Cofficiency switching grants workspace selection, not additional role permissions.
- External users never receive or invoke tenant-switch controls.

---

## 11. Tenant and User Management UX

### 11.1 Tenant switcher

- Place immediately to the left of the upper-right user avatar.
- Visible only to Cofficiency users.
- Show active tenant name and a dropdown of active tenants.
- Switching uses a POST action and redirects safely back to an internal URL.
- The selected tenant applies on the next request to every tenant-owned surface.
- Persist the selection as the user's `last_active_tenant_id`.
- If an active tenant is archived while selected, fall back to Cofficiency.

### 11.2 Tenant management

- Available only to Cofficiency administrators.
- List tenants with active/archived state.
- Create a tenant using name; generate/validate a unique stable slug.
- Edit permitted metadata.
- Archive/reactivate non-protected tenants.
- Do not hard-delete tenants in v1.
- Cofficiency cannot be archived or renamed.

### 11.3 User management

- User list shows only the active tenant's users.
- User counts by role are calculated only within the active tenant.
- New users automatically receive `active_tenant.id`.
- No tenant selector appears on add/edit forms.
- Tenant assignment is never editable after creation.
- Direct edit/toggle/avatar routes reject users outside the active tenant.
- An external user with user-edit permission can manage only users in their home tenant.
- Existing self-deactivation and authorization restrictions remain.

---

## 12. Activity and Reporting Semantics

Every operational log row stores the tenant context at event time.

Examples:

- AdvantageFirst user performs an action → AdvantageFirst log.
- Cofficiency user selects AdvantageFirst and creates an agent → AdvantageFirst log, actor remains the Cofficiency user.
- Cofficiency user selects Cofficiency and creates a Cofficiency user → Cofficiency log.

The actor's `user_id` and event's `tenant_id` serve different purposes and must both be retained.

Special cases:

- Login activity uses the resolved tenant after login: home tenant for external users, remembered active tenant for Cofficiency users.
- Tenant-switch activity should be attributed to the destination tenant and include a dedicated `tenant.switched` action.
- Historical `UserActivityLog`, `LlmRequestLog`, and `ApiRequestLog` rows migrate to AdvantageFirst, including rows whose actor becomes a Cofficiency user.
- Reporting lists, summary cards, users, models, and integrations are filtered to the active tenant.
- Global release notes remain visible but do not cause customer operational totals to include other tenants.

---

## 13. Migration Strategy

The Alembic migration must preserve existing data.

1. Create `tenant`.
2. Insert Cofficiency (`cofficiency`, protected) and AdvantageFirst (`advantagefirst`).
3. Add nullable tenant columns and the tenant-feature override table.
4. Assign the existing system `admin` user's home tenant to Cofficiency.
5. Assign every other existing user's home tenant to AdvantageFirst.
6. Set the system admin's `last_active_tenant_id` to AdvantageFirst so the existing working context remains available after upgrade.
7. Assign all existing tenant-owned operational/configuration records to AdvantageFirst.
8. Assign all existing activity, LLM request, and API request logs to AdvantageFirst regardless of actor.
9. Create tenant-relative unique constraints/indexes.
10. Make required tenant columns non-null.

Migration verification must explicitly assert:

- Exactly one protected Cofficiency tenant exists.
- AdvantageFirst exists.
- No required tenant ID is null.
- Existing record counts are unchanged.
- The system admin belongs to Cofficiency.
- All historical logs belong to AdvantageFirst.
- Existing conversations, agents, integrations, models, and attributes belong to AdvantageFirst.

---

## 14. Feature Flags

- `FeatureFlag` remains the global catalogue.
- All current global defaults remain enabled.
- The System Config feature-flags tab displays effective state for the active tenant.
- Toggling creates or updates `TenantFeatureFlag`; it does not mutate the global flag row.
- Navigation and route behavior use the same effective-state resolver.
- A hidden navigation item is not an authorization boundary. Disabled feature routes must also reject or redirect appropriately.
- Creating a tenant requires no override rows; it inherits enabled defaults.

---

## 15. skunkBOX and Knowledge-Base Boundary

Until skunkBOX accepts tenant ID:

- Integrations and encrypted API keys are tenant-owned.
- AI agents are tenant-owned and reference only same-tenant integrations.
- Conversation and Learning Center/knowledge-base proxy calls use only the active tenant's selected agent/integration.
- Attachment upload/download authorization follows the owning conversation's tenant.
- No cross-tenant integration ID or agent ID may be accepted, even from a forged request.

Future skunkBOX work will add tenant ID to APIs and AI Asset/Component management. That work is outside this implementation but must not require changing Cophy's core home/active tenant semantics.

---

## 16. Security Acceptance Criteria

1. An external user cannot change active tenant by altering request data, cookies, sessions, or URLs.
2. An external user cannot list, read, edit, toggle, archive, or reference another tenant's records.
3. A Cofficiency user cannot access a selected tenant's page without the existing required role permission.
4. A forged agent/integration/model/user/conversation ID from another tenant is rejected.
5. Tenant switching accepts only active tenants and is CSRF-protected according to project conventions.
6. User tenant assignment cannot be mutated through UI or crafted requests.
7. Bulk operations cannot affect another tenant.
8. Reporting never mixes tenant-owned rows.
9. Feature flags cannot leak state or navigation across tenants.
10. Global documentation and release notes remain available without exposing tenant data.

---

## 17. Functional Acceptance Criteria

1. Cofficiency and AdvantageFirst are created during migration.
2. Existing admin signs in as a Cofficiency user and initially operates in AdvantageFirst.
3. Existing external users and business data continue working under AdvantageFirst.
4. Cofficiency users see a tenant switcher left of the avatar.
5. External users do not see the switcher.
6. A Cofficiency user's most recent tenant persists across logout/login and browser sessions.
7. Cofficiency selected as active tenant shows Cofficiency users only and no AdvantageFirst operational assets.
8. Creating a user assigns the active tenant without a selectable tenant field.
9. Tenant assignment remains immutable.
10. Models, attributes, integrations/API keys, agents, conversations, knowledge-base access, dashboards, feature flags, and reporting follow active tenant.
11. Historical reports appear under AdvantageFirst.
12. New Cofficiency-user actions appear in the selected tenant's report.
13. User Documentation and Release Notes do not change when switching tenants.

---

## 18. Phased Delivery

### Phase 1 — Tenant schema and safe migration

Add tenant models/columns, seed Cofficiency and AdvantageFirst, migrate historical ownership, update constraints, and add migration/model tests. Do not expose switching yet.

### Phase 2 — Active tenant context, tenant administration, and switcher

Add the centralized context service, tenant management UI, active-tenant switch endpoint, last-used persistence, header switcher, and tenant-aware activity attribution.

### Phase 3 — Tenant-isolated user management

Filter user lists/counts, bind creation to active tenant, enforce immutable tenant assignment, and secure all direct user operations.

### Phase 4 — Tenant-isolated configuration and feature flags

Scope models, attributes, integrations/API keys, and AI agents; validate same-tenant relationships; implement per-tenant feature overrides while leaving global configuration global.

### Phase 5 — Conversations, knowledge base, and dashboard

Scope agents and conversations end-to-end, secure all conversation/message/attachment/proxy paths, isolate Learning Center access, and make dashboard statistics tenant-aware.

### Phase 6 — Reporting, audit, and isolation hardening

Filter reporting and request logs, verify activity attribution, audit all direct/bulk routes, add cross-tenant regression tests, and update architecture/user documentation.

Each phase has a corresponding implementation prompt in `docs/prompts/`.

---

## 19. Rollout and Operational Notes

- Back up the production database before Phase 1 migration.
- Test the migration against a copy of production data.
- Deploy phases in order.
- Do not create customer tenants until the relevant isolation phases are deployed.
- Treat tenant isolation failures as security defects.
- Avoid relying on SQLAlchemy global query hooks in v1; explicit service helpers and query predicates are easier to audit in this codebase.
- Once Phase 6 passes, perform a manual two-browser test with one Cofficiency user and two external tenant users.

---

## 20. Resolved Questions

All material product questions raised during discovery are resolved:

- One immutable home tenant per user: **yes**
- Cofficiency tenant identifies internal users: **yes**
- Every Cofficiency user may switch active workspace: **yes**
- Existing permissions still apply after switching: **yes**
- Roles remain global: **yes**
- Cofficiency is an empty operational workspace initially: **yes**
- Existing business data and historical logs migrate to AdvantageFirst: **yes**
- Existing system admin belongs to Cofficiency but prior activity remains AdvantageFirst: **yes**
- Tenant-specific integration/API configuration provides interim skunkBOX isolation: **yes**

