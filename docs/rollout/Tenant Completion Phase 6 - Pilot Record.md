# Tenant Completion Phase 6 — Pilot, Monitoring, and Decision Record

This record must be completed in the target environment. Empty approval
fields are deployment blockers, not implied approval.

## Pilot

- Pilot tenant:
- Tenant UUID:
- Observation window (UTC):
- Cofficiency owner:
- Customer tester username/role:
- Cophy revision:
- skunkBOX revision:
- Cophy/skunkBOX backup references:
- Migration rehearsal evidence:
- Approved collection inventory:
- Approved Agent inventory:

## Enablement

- [ ] Cofficiency-only `ai_quality` override enabled and full workflow passed
- [ ] Pilot is active, synchronized, and has required Integrations
- [ ] Pilot-only `ai_quality` override enabled
- [ ] No other customer override was enabled
- [ ] Customer's own user signed in (not only a switched Cofficiency user)

## Pilot workflow

Record timestamp, actor, target IDs, outcome, and correlation ID.

| Test | UTC | Actor | IDs | Correlation ID | Outcome/evidence |
|---|---|---|---|---|---|
| Shared collection read/search/download | | | | | |
| Shared collection mutation denied | | | | | |
| Private collection cross-tenant denial | | | | | |
| Shared Agent read/use | | | | | |
| Shared Agent mutation denied | | | | | |
| Private Agent create/edit/collections/archive/reactivate | | | | | |
| Component create/edit/promote | | | | | |
| Dataset create/import | | | | | |
| Experiment run/results | | | | | |
| Cross-tenant Component/Dataset/Experiment denial | | | | | |
| Citation/RAG tenant safety | | | | | |

## Monitoring and incidents

| UTC/window | Metric or event | Tenant | Expected | Observed | Correlation IDs | Action/status |
|---|---|---|---|---|---|---|
| | 403/404 rate | | | | | |
| | Management API errors | | | | | |
| | p50/p95 latency | | | | | |
| | Tenant sync drift | | | | | |
| | Experiment jobs | | | | | |

## Rollback drill

- [ ] Pilot feature override disabled and access disappeared without data loss
- [ ] Service credential revocation failed closed; replacement credential restored access
- [ ] Test Shared resource unshared after dependency validation
- [ ] Test tenant archived; new operations failed closed and history remained
- [ ] Backup restore command rehearsed against a disposable copy

Evidence:

## Go / no-go

- Decision: **PENDING — GO / NO-GO**
- Scope authorized:
- Conditions:
- Cofficiency approver:
- Customer acknowledgement:
- Decision UTC:
- Next review UTC:
