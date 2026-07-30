# Phase 1 — skunkBOX Internal Tenant Access Hardening

**Target system:** `saas-platform`  
**Product name:** skunkBOX  
**System role:** Cofficiency administrative/backend platform and authoritative tenant/AI-asset store  

Do not implement this phase in `saas-mortgage` (the customer-facing Client Portal).

Read before starting:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/TENANT_ISOLATION_AUDIT.md`
- `saas-mortgage/docs/prompts/Cross-System Tenant AI Assets - PRD.md`
- Existing access/permission helpers and all document/chat routes

---

## Goal

Close the two medium-severity internal-access findings from the tenant audit:

1. Authenticated internal users can reach document routes without consistent document permissions.
2. Internal users with chat access can open API-originated customer conversation transcripts because `_assert_owner()` is a no-op.

Customer-facing APIs already enforce tenant isolation. This phase hardens the skunkBOX administrative UI so customer documents and conversations are not broadly visible to every internal account.

---

## Required policy

Implement explicit support-access authorization:

- Cofficiency administrators may access all tenants for legitimate administration/support.
- Non-admin internal users may access only the administrative tenant context and resources permitted by their existing role.
- Cross-tenant customer document/transcript access requires a dedicated permission or an admin role.
- Tenant selection alone does not grant access.
- Customer API behavior must remain unchanged.

If the current role system supports page/action permissions cleanly, add permissions such as:

- `documents:view`
- `documents:edit`
- `customer_conversations:view`

Use existing conventions rather than introducing a second authorization framework.

---

## Documents

Audit every route in `app/routes/documents.py`, including:

- Lists
- View
- Create/upload
- Edit
- Download
- Collection membership
- Reprocess
- Archive/delete-like actions
- AJAX/JSON helpers

Apply the correct `permission_required` level. For direct IDs:

- Resolve the document/collection.
- Apply administrative tenant context.
- Require explicit cross-tenant support permission when the record is not in the current admin context.
- Return safe 404/403 without leaking private metadata.

Shared Cofficiency collections remain visible/readable under their existing rules. This phase must not allow customer tenants to mutate Shared resources.

---

## Conversations

Replace the no-op `_assert_owner()` in `app/routes/chat.py` with a real authorization check.

Differentiate:

- Internal skunkBOX conversations without a tenant
- Tenant API-originated conversations with `Conversation.tenant_id`
- Shared-Agent usage whose conversation belongs to the calling customer tenant

Rules:

- Admin/support permission may inspect customer conversations.
- Ordinary internal chat permission alone is insufficient for cross-tenant customer transcripts.
- View, message, attachment, export, archive, and related direct-ID operations use the same authorization.
- Do not break service/API access to conversations already authorized by API key tenant.

Log support access to customer documents/conversations with actor, tenant, resource, action, and result.

---

## Tests

Create Cofficiency admin, limited internal user, and two customer tenants.

Cover:

1. Limited internal user cannot browse/download another tenant's private document.
2. Admin/support-authorized user can perform approved support access.
3. Shared collection visibility remains correct.
4. Limited user cannot open another tenant's API conversation URL.
5. Conversation attachments/exports inherit the same restriction.
6. Customer APIs remain tenant-isolated and unchanged.
7. Support-access activity is audited.
8. Existing role/permission management continues working.

Run the complete test suite. Update `docs/TENANT_ISOLATION_AUDIT.md`, architecture/permissions documentation, and `CHANGELOG.md`.

---

## Deliverables

- Consistent document route permissions
- Real conversation transcript authorization
- Support-access audit logging
- Regression tests
- Updated tenant audit and permission documentation

