# Phase 6 — Shared Resource Curation and Pilot Rollout

**Coordinating system:** `saas-mortgage` — Cophy Portal / Client Portal  
**Backend system involved:** `saas-platform` — skunkBOX  

This is an operational phase spanning both systems. skunkBOX is authoritative for tenants, Shared collections, Shared Agents, Components, Datasets, and Experiments. The Client Portal controls customer access through tenant context, permissions, and feature flags.

Read:

- `docs/ROLLOUT_PLAN.md`
- `docs/MIGRATION_REHEARSAL.md`
- `docs/OPERATIONS_RUNBOOK.md`
- Tenant audits in both repositories
- All completed Tenant Completion phases

---

## Goal

Safely curate Shared Cofficiency knowledge/Agents and execute the first real target-environment rollout.

Do not automatically mark resources Shared. Sharing is a product/content decision requiring Cofficiency approval.

---

## Part A — Preflight

For both target environments:

- Confirm clean worktrees/deployed revisions.
- Run full test suites with no unexplained failures.
- Back up databases.
- Rehearse migrations against copies of target data.
- Verify migration heads/current revisions.
- Confirm Cofficiency/AdvantageFirst UUID mapping.
- Confirm service credentials/capabilities and secret configuration.
- Run tenant reconciliation.
- Confirm no local-only or ambiguous tenants.
- Confirm archived tenants fail closed.

Produce an evidence report with commands, timestamps, counts, and outcomes.

---

## Part B — Shared collection review

Generate a review inventory from skunkBOX:

- Collection name/ID
- Document count
- Document sources
- Current owner
- Agents using it
- Licensing/public-domain rationale
- Sensitive/proprietary-content indicators
- Proposed Shared decision

Cofficiency stakeholder must approve each collection.

After approval:

- Mark only approved Cofficiency collections Shared.
- Verify all documents remain in exactly one collection.
- Verify customer tenants can read/search/download but cannot mutate.
- Verify citations and RAG searches remain tenant-safe.

Do not share individual documents outside their owning collection.

---

## Part C — Shared Agent review

Generate an Agent dependency inventory:

- Agent name/ID
- Collections
- Skills/tools
- Models/integrations
- MCP tools
- Prompt/instructions
- Proposed Shared decision

Before sharing:

- Every collection dependency is Shared.
- Every skill/tool is globally safe.
- Tenant-injected MCP context cannot be overridden.
- No private Component/Dataset/Experiment dependency exists.

Obtain explicit approval, then mark approved Agents Shared.

---

## Part D — Enablement

1. Enable AI Assets & Quality for Cofficiency only.
2. Exercise the full workflow in the target environment.
3. Select one pilot customer.
4. Confirm integrations and tenant sync.
5. Enable the feature flag only for that tenant.
6. Test with the customer's own user, not only a switched Cofficiency administrator.
7. Verify Shared and private Agent/knowledge behavior.
8. Verify Component/version/Dataset/Experiment workflow.
9. Monitor logs, denials, sync drift, errors, latency, and jobs.

Do not expand until the agreed pilot observation period completes.

---

## Rollback

Document and test:

- Disable tenant feature override
- Revoke service credential
- Unshare a resource after dependency validation
- Archive tenant
- Restore database backup if migration failure occurs

Use disable/archive/revoke rather than deleting data.

---

## Deliverables

- Target-environment migration evidence
- Approved Shared collection inventory
- Approved Shared Agent inventory
- Pilot test record
- Monitoring/incident record
- Go/no-go decision
- Updated rollout plan with completed checkboxes and dates

