# Calls Tenancy Readiness Gate

**Status:** Blocked by missing Calls product and integration contracts  
**Reviewed:** 2026-07-30  
**Systems:** Cophy Portal (`saas-mortgage`) and, if selected by the future
architecture, skunkBOX (`saas-platform`)

## Decision

No Calls model, migration, route, feature flag, navigation item, worker,
webhook, API, or empty placeholder has been created.

`docs/prompts/Tenant Completion - Prompt - Phase 7 - saas-mortgage.md`
explicitly says not to create speculative Calls structures until the Calls
product requirements and upstream data source are known. Repository review
found no Calls-specific PRD or ingestion/API contract. Existing references
to “call transcripts” are generic chatbot messages or Dataset examples;
they do not define a Call root record, source account, webhook trust model,
processing lifecycle, or customer UI.

## Required decisions before implementation

### Product and ownership

- What is the minimum Call product workflow and which surfaces ship first?
- Which system is authoritative for the Call root and each artifact?
- Is a Call always private? The default must be yes unless a separately
  approved Calls PRD defines sharing.
- What retention, legal hold, deletion, export, and consent rules apply to
  recordings and transcripts?
- Which roles may list, listen, download, export, reprocess, or evaluate?

### Source and trusted tenant mapping

- What are the first ingestion sources: browser upload, telephony/provider
  sync, webhook, API, batch import, or some combination?
- What credential or external-account record authenticates each source?
- What immutable mapping binds that credential/account to one local tenant
  and skunkBOX UUID?
- What happens when an external account maps to zero or multiple tenants?
  Required behavior is reject and quarantine, never guess.
- What is the external Call ID uniqueness boundary: tenant + source +
  external account + external Call ID?
- What replay signature, timestamp window, and idempotency mechanism apply
  to webhooks?

### Data contract

- Call fields, states, timestamps, participants, direction, duration, and
  source metadata.
- Recording/audio/video storage location, encryption, MIME/size rules, and
  signed-download contract.
- Transcript format, speakers, revisions, redaction, and provenance.
- Summary, extracted facts/actions, attachments, evaluations, and quality
  result schemas.
- Processing-job states, retry/dead-letter behavior, and event/audit schema.
- Whether skunkBOX receives full artifacts, references, or evaluation-only
  payloads.

### Operations

- Backfill source and trusted historical tenant mapping, if historical Calls
  exist. Tenant must never be inferred solely from a mutable user,
  Integration, or account after the event.
- Queue technology and the exact tenant-bearing job payload.
- Failure recovery, replay, reconciliation, retention, monitoring, and
  incident-response expectations.
- Named pilot tenant and observation/rollback plan. The future `calls`
  feature flag must default off and use a tenant override for the pilot.

## Non-negotiable implementation contract

Once the decisions above are approved:

1. Every Call root has a required, immutable `tenant_id`.
2. Every dependent artifact stores tenant directly where it is independently
   addressed, queued, exported, logged, or processed; otherwise it inherits
   through a required Call relationship.
3. Ingestion resolves tenant only from a validated server-side
   credential/account mapping. Browser or webhook `tenant_id` values are
   ignored as authority.
4. Tenant is persisted before background work starts and included in every
   job/event payload. Workers reload and revalidate Call, artifact, source,
   and tenant relationships before work.
5. Cophy lists, search, filters, counts, dashboards, exports, and direct
   URLs enforce the active tenant plus existing permissions.
6. skunkBOX independently binds the service credential and tenant UUID and
   safely denies cross-tenant identifiers if it stores/processes Calls.
7. Event-time activity, usage, and API logs store the tenant under which the
   event occurred.
8. Archived tenants reject new ingestion and processing without deleting
   history.

## Required acceptance fixture

Tests must use Cofficiency, Customer A, and Customer B, including two
sources with colliding external Call IDs. They must cover:

- trusted ingestion mapping and ambiguous-mapping rejection;
- browser/webhook tenant spoofing and replay;
- cross-tenant list, search, count, dashboard, direct URL, and export denial;
- transcript, recording, attachment, participant, evaluation, and job
  isolation;
- queue payload tenant propagation and worker-time revalidation;
- tenant switch invalidating a previously-open Call URL;
- archived-tenant failure;
- pilot-only feature flag behavior;
- event-tenant reporting and audit attribution;
- Calls remaining private with no accidental Shared semantics.

## Unblocking artifact

The next implementation turn must be supplied an approved Calls PRD and
source/API contract answering the sections above. At that point this file
becomes the tenancy/security appendix to that PRD and the implementation can
be split into migrations, ingestion, workers, UI/API, and rollout phases.
