# Tenant Completion Phase 6 — Preflight Evidence (Local Dev (not production))

- Generated (UTC): `2026-07-30T19:16:36.163105+00:00`
- Cophy revision: `380d2752249b20dbe17832361f2d982b0167ef2b`
- Worktree: `DIRTY — no-go for deployment`
- Migration head command: `ok` — `n4o5p6q7r8s9 (head)`
- skunkBOX URL + service secret configured: `no`

## Tenant registry

| Tenant | UUID | Active | Sync status | Users | Agent pointers | AI Quality override |
|---|---|---:|---|---:|---:|---|
| AdvantageFirst | `7c1e6b44-5a3f-4e9a-9b52-1e3a7f6d2c88` | yes | synced | 1 | 4 | inherited |
| Cofficiency | `3f9d9a2e-2b7a-4a63-9d1a-8e4c9c9b7a10` | yes | synced | 1 | 0 | inherited |

- Cofficiency UUID: `3f9d9a2e-2b7a-4a63-9d1a-8e4c9c9b7a10`
- AdvantageFirst UUID: `7c1e6b44-5a3f-4e9a-9b52-1e3a7f6d2c88`
- Unsynced/ambiguous local tenants: `0`
- Archived tenants: `0` (must fail closed in target smoke tests)
- Active AI Agent Integrations: `1`
- Active Documents Integrations: `1`

## Management API monitoring baseline

- Local management-call audit rows: `0`
- Secrets and request bodies are intentionally excluded from this report.

## Test and migration verification completed after generation

- Cophy migrations: `n4o5p6q7r8s9 (head)` current = head.
- skunkBOX migrations: `th90123456ta (head)` current = head.
- Cophy suite: `138 passed` on 2026-07-30.
- skunkBOX suite: `209 passed` on 2026-07-30.
- These local results do not satisfy the separate requirement to rerun
  against the clean revisions deployed in the target environment.

## Deployment gates

- [ ] Cophy worktree clean
- [x] Cophy migration head resolved
- [ ] Service URL and secret configured
- [x] Cofficiency and AdvantageFirst present
- [x] No local-only or unsynced tenants
- [ ] Target database backups recorded and restore-tested
- [ ] Migrations rehearsed against target-data copies
- [ ] skunkBOX UUIDs independently compared with this table
- [ ] Archived-tenant fail-closed smoke test passed
- [x] Full suites passed locally (target deployed-revision rerun remains required)

## Human-controlled gates (never automated)

- [ ] Every proposed Shared collection has explicit Cofficiency approval
- [ ] Every proposed Shared Agent has explicit Cofficiency approval
- [ ] Pilot tenant and observation window are named
- [ ] Pilot customer's own user completed the workflow
- [ ] Go/no-go decision signed and dated

## skunkBOX curation inventory

Authoritative inventory: `/Users/dmitrychechuy/Workspace/saas-platform/docs/rollout/Shared Resource Review - Local Dev.md`
