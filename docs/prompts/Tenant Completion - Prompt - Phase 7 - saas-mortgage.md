# Phase 7 — Tenant-Ready Calls Foundation

**Primary target system:** `saas-mortgage` — Cophy Portal / Client Portal  
**Backend integration target when applicable:** `saas-platform` — skunkBOX

Use this prompt when the Calls feature is ready to be implemented. Do not create speculative empty tables/routes before the Calls product requirements and upstream data source are known.

Read both tenant PRDs, the current Client Portal tenant context/audit, and any Calls-specific PRD/API contract.

---

## Goal

Ensure Calls is tenant-owned from its first production implementation rather than retrofitting isolation later.

---

## Required ownership

Every Call root record must have an immutable required tenant owner.

Dependent records inherit or store tenant where needed:

- Participants/contacts
- Audio/video metadata
- Transcripts
- Summaries
- Extracted facts/actions
- Attachments
- AI evaluations/quality results
- Processing jobs
- API/webhook events
- Usage/activity logs

Do not infer historical tenant solely from a mutable user, integration, or external account.

---

## Ingestion

For every source—upload, integration sync, webhook, API, or background import:

- Resolve tenant from trusted server-side integration/account mapping.
- Never trust browser/webhook tenant ID without credential validation.
- Reject ambiguous mappings.
- Store tenant before background work starts.
- Carry tenant through every queue/job payload.
- Revalidate relationships at worker execution.
- Make external-call IDs unique within the appropriate tenant/source boundary.

---

## Client Portal behavior

- Lists, search, filters, counts, dashboards, and exports use active tenant.
- Direct Call/transcript/attachment URLs enforce active tenant.
- Cofficiency switching changes workspace but does not reassign Calls.
- Existing role permissions remain additive.
- Feature flag is tenant-specific and disabled by default during pilot.
- User Documentation and Release Notes remain global.
- Activity/reporting attributes actions to active/event tenant.

---

## skunkBOX behavior

If skunkBOX stores or processes any Call artifact:

- Add authoritative tenant ownership there.
- Bind API/service credential and tenant UUID.
- Enforce tenant independently.
- Use Shared semantics only if a separate approved Calls PRD introduces them; Calls are private by default.
- Return safe denial for cross-tenant identifiers.

---

## Tests

Use Cofficiency and two customer tenants. Cover:

- Ingestion mapping
- Cross-tenant list/direct/export denial
- Transcript and attachment isolation
- Worker tenant propagation
- Reporting/count isolation
- Tenant switch invalidation
- Webhook/API spoofing
- Archived tenant behavior
- Feature-flag pilot
- No Shared/private confusion

Update architecture and tenant audits before enabling Calls.

