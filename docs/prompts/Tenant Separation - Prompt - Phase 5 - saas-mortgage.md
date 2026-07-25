# Phase 5 — Conversations, Knowledge Base, and Dashboard

You are working on `saas-mortgage` (Cophy Portal).

Read:

- `docs/prompts/Tenant Separation - PRD.md`
- Completed Phases 1–4
- All conversation, attachment, Learning Center, dashboard, and skunkBOX proxy routes
- Any repository agent instructions

Implement only Phase 5.

---

## Goal

Enforce active-tenant ownership throughout conversations and knowledge-base access, and make dashboard operational statistics tenant-aware.

---

## Conversation creation and lists

- List only active-tenant AI agents.
- Create a conversation with `tenant_id=active_tenant.id`.
- Accept only an active AI agent belonging to active tenant.
- Ensure the current external user's home tenant matches active tenant by resolver design.
- In conversation tabs:
  - “Mine” means actor's conversations within active tenant.
  - “All” means all conversations within active tenant when role scope permits.
  - “Favorites” means actor's favorites within active tenant.
- Agent/user/date filters operate only within active tenant.
- Filter dropdown users and agents to active tenant.
- Auto-cleanup of empty conversations includes tenant predicate.
- Last-used-agent calculations include tenant predicate.

For a Cofficiency user, “Mine” must be filtered by both their user ID and selected tenant so their work in customer A never appears in customer B.

---

## Direct conversation operations

Audit and protect every route that receives a conversation/message/attachment/agent identifier, including:

- View conversation
- Send message
- Upload attachment
- Download attachment
- Archive
- Favorite/unfavorite
- Start/continue adhoc or agent chat variants
- Learning Center document access reached through a conversation/agent
- Any AJAX helper route

Requirements:

- Resolve the owning conversation and verify `conversation.tenant_id == active_tenant.id` before further access.
- Existing “own” versus “all” permission scope applies only after tenant match.
- Do not allow a Cofficiency user to keep a customer A conversation open, switch to customer B, and continue using the old URL.
- Message and attachment ownership must be established through a matching active-tenant conversation.
- Prefer 404 for cross-tenant direct-object access.
- Bulk archive/update operations include tenant predicates.

---

## Cross-model invariants

On create/use:

- `AgentConversation.tenant_id == AiAgent.tenant_id`
- `AgentConversation.tenant_id == active_tenant.id`
- `AiAgent.tenant_id == Integration.tenant_id`

Do not rely only on relationships created in Phase 4. Validate at request boundaries to reject forged identifiers.

---

## skunkBOX and knowledge base

Continue using tenant-owned Integration credentials as the interim isolation boundary.

- Every chat call uses the conversation's same-tenant agent/integration.
- Every attachment upload/download uses the owning conversation's same-tenant integration.
- Every Learning Center / knowledge-base request uses only an active-tenant agent/integration.
- Any agent selector used by Learning Center contains only active-tenant agents.
- Cross-tenant document/proxy access is rejected locally before making an outbound request.
- Do not send a speculative tenant ID to skunkBOX; that API change is future work.

Review API request logging call sites and pass active/owning tenant information using the Phase 1/2 logging foundation. Final reporting UI comes in Phase 6.

---

## Dashboard

Update dashboard queries:

- Users: active tenant only.
- LLM models: active tenant only.
- Integrations: active tenant only.
- Attributes: active tenant only.
- Any agent/conversation/call/component metrics now or later: active tenant only.
- Roles remain global templates. If role count remains on the dashboard, label/treat it as global rather than implying tenant ownership.
- Release notes and recent releases remain global and visible.

Apply equivalent dashboard-card behavior inside Reporting where shared code makes that safe, but leave the complete Reporting query audit for Phase 6.

---

## Global surfaces

Verify switching active tenant does not change or hide:

- User Documentation
- Release Notes

These pages must not accidentally run tenant-owned broad queries while rendering shared content.

---

## Tests

Create conversations/assets in at least two customer tenants plus Cofficiency.

Cover:

1. Agent choices are active-tenant only.
2. New conversation receives active tenant.
3. Forged cross-tenant agent ID is rejected.
4. Mine/all/favorites and filters never mix tenants.
5. Cofficiency actor's “Mine” conversations remain separated by selected tenant.
6. Old conversation URL fails after switching away from its tenant.
7. Cross-tenant send/archive/favorite/upload/download IDs are rejected.
8. Attachment ownership is enforced through conversation tenant.
9. Knowledge-base routes cannot use another tenant's agent/integration.
10. Outbound API log receives owning/active tenant.
11. Dashboard operational counts change with tenant.
12. Roles/releases behave globally as specified.
13. User Documentation and Release Notes remain visible across tenant switches.

Run the full available test suite.

---

## Deliverables

- Fully tenant-safe conversation and attachment routes
- Tenant-safe knowledge-base/skunkBOX proxy selection
- Tenant-aware dashboard
- Cross-tenant security tests
- A list of all audited identifier-based routes in the completion summary
