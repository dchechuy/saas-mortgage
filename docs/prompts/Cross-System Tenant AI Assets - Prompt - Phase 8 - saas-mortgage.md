# Phase 8 — Cross-System Audit and Rollout

This is a coordinated final phase across `saas-platform` and `saas-mortgage`, led from the Cophy repository.

Read the cross-system PRD, all completed phases, both repositories' instructions, API contract, migrations, audits, and operational documentation.

---

## Goal

Prove tenant isolation and synchronization end to end before enabling customer AI Asset management.

---

## Migration rehearsal

Against disposable production-like copies:

- Upgrade skunkBOX and confirm all legacy data is Cofficiency-owned.
- Confirm AdvantageFirst exists but received no legacy skunkBOX records.
- Audit Document-to-Collection cardinality before enforcing one collection.
- Review and explicitly mark safe public collections Shared.
- Review and explicitly mark safe Cofficiency Agents Shared.
- Upgrade Cophy and reconcile Cofficiency/AdvantageFirst UUIDs.
- Compare record counts, ownership, constraints, and archived state.
- Exercise rollback/forward recovery where supported.

Document exact commands and results.

---

## Cross-system adversarial matrix

Use:

- Cofficiency administrator
- Cofficiency limited user
- AdvantageFirst customer user
- Second customer tenant/user
- Private resources in both customers
- Shared Cofficiency collection and Agent
- Components, versions, datasets, experiments, attachments, and logs

Test:

- Forged tenant UUID with valid/invalid credentials
- Ordinary API key calling management/provisioning API
- Customer A IDs used in Customer B requests
- Shared resource mutation
- Shared Agent with private dependency
- Tenant Agent with cross-tenant private collection
- Component/Dataset/Experiment tenant mismatch
- Switch tenant during editing/upload/polling/download
- Archived tenant API and UI behavior
- Revoked service credential
- Mirror drift and reconciliation
- Retried tenant create/component create/experiment run
- Vector search/RAG leakage
- Background job tenant confusion
- Counts, filters, exports, error messages, logs, and HTML leakage

Both systems must reject independently where applicable.

---

## Ownership audit

Produce/update audit documents in both repositories classifying every relevant model/query:

- Tenant-owned
- Cofficiency-owned Shared-capable
- Inherited ownership
- Intentionally global

Search direct gets, joins, bulk mutations, raw SQL, workers, exports, reports, MCP/internal tools, downloads, and API filters. Resolve every unexplained global query.

---

## Observability and operations

Add or verify:

- Tenant UUID in structured API/job logs
- Credential/capability audit trail
- Sync/reconciliation status and failure alerting
- Metrics for cross-tenant denial, sync drift, API latency/error, and job failures
- Secret redaction
- Runbooks for partial provisioning failure, archival, key rotation, reconciliation, unsharing, and incident response

---

## Documentation

Update both systems:

- Architecture
- API contract
- User/admin manuals
- Quick start/configuration
- Environment variables/secrets
- Migration/runbook
- Tenant and Shared semantics
- Customer Component/quality workflow

Explicitly document that Shared means Cofficiency-owned and read-only to all tenants—not jointly owned.

---

## Rollout

1. Deploy skunkBOX schema/registry with customer management APIs disabled.
2. Rehearse and validate migration.
3. Configure service credential and synchronize Cophy.
4. Enable Shared knowledge/Agents for internal testing.
5. Enable Component/quality feature flags for Cofficiency.
6. Enable one pilot customer tenant.
7. Monitor and audit.
8. Expand tenant by tenant.

Provide a rollback/disable strategy using feature flags and credential revocation without deleting data.

---

## Acceptance

Map evidence to every PRD acceptance and security criterion. Do not declare complete until:

- Full tests pass in both repositories.
- Migration/reconciliation evidence is recorded.
- Browser smoke tests pass.
- No unresolved cross-tenant access path remains.
- Pilot enablement and rollback steps are documented.

Update required changelogs in each repository.

