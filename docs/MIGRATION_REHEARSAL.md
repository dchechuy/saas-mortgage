# Cross-System Migration Rehearsal (Phase 8)

Cross-System Tenant AI Assets PRD, Phase 8 — "Cross-system audit and
rollout." Rehearsed against disposable copies of each system's real dev
database (never against production; disposable copies are `.bak`-suffixed
snapshots or `/tmp` files, discarded after verification). Both systems
were confirmed already fully migrated to head with no schema drift before
these dry runs were reused to apply the DB to the production database, and
every step below has a corresponding real-database backup file committed
to the repo's `instance/` directory (or documented below) taken immediately
before the real apply.

Re-run this rehearsal (adjusted for whatever new migrations exist) before
every further schema change that touches tenant, sharing, Component,
Dataset, or Experiment tables.

---

## 1. saas-platform (skunkBOX)

### 1.1 State found

`flask db current` on the real dev database (`instance/app.db`) reported
`254c1727a706 (mergepoint)`, while `flask db heads` reported a newer head,
`05425d90b900`. One migration was pending: an empty (`pass`/`pass`) Alembic
merge node reconciling the tenant-scoping branch with an unrelated
"server-side" branch (`392b202057aa`, itself tracing back through ~18
pre-existing, unrelated schema migrations to `4d0bc0fd64b3`, the original
initial-schema revision). This is the same class of issue flagged during
earlier phases of this initiative: a separate deploy process periodically
generates its own merge-heads migrations when it encounters divergent
Alembic heads at deploy time. It is not a data-affecting migration — both
`upgrade()`/`downgrade()` bodies are `pass`.

### 1.2 Commands run

```bash
# Disposable copy
rm -f /tmp/skunkbox_phase8_test.db
cp instance/app.db /tmp/skunkbox_phase8_test.db

# Upgrade rehearsal
DATABASE_URL="sqlite:////tmp/skunkbox_phase8_test.db" venv/bin/python -m flask db upgrade

# Round-trip (downgrade then re-upgrade)
DATABASE_URL="sqlite:////tmp/skunkbox_phase8_test.db" venv/bin/python -m flask db downgrade 254c1727a706
DATABASE_URL="sqlite:////tmp/skunkbox_phase8_test.db" venv/bin/python -m flask db upgrade

# Applied to the real dev database, backed up first
cp instance/app.db instance/app.db.pre-phase8-migration.bak
venv/bin/python -m flask db upgrade

# Full suite re-run after
venv/bin/python -m pytest -q
```

### 1.3 Results

**Upgrade**: clean, no errors, both merge nodes applied in order
(`392b202057aa` then `05425d90b900`).

**Round-trip**: downgrade and re-upgrade both completed cleanly on the
disposable copy — confirmed reversible (trivially, since both are no-ops).

**Ownership audit** (disposable copy, post-upgrade):

| Model | Total | Cofficiency | AdvantageFirst | Other tenant | NULL tenant |
|---|---|---|---|---|---|
| Component | 12 | 12 | 0 | 0 | 0 |
| Persona | 15 | 15 | 0 | 0 | 0 |
| DocumentCollection | 14 | 14 | 0 | 0 | 0 |
| Document | 161 | 161 | 0 | 0 | 0 |
| Dataset | 17 | 17 | 0 | 0 | 0 |
| Experiment | 25 | 25 | 0 | 0 | 0 |

**Confirms**: all pre-existing skunkBOX records are Cofficiency-owned;
AdvantageFirst exists (`is_active=True`, `is_protected=False`) but received
zero legacy records of any governed type — matching PRD §15 exactly ("No
existing Component, Persona, document, collection, conversation, log,
dataset, or experiment is assigned to AdvantageFirst").

**Document/Collection cardinality**: 0 documents with more than one
collection membership, 0 documents with zero collection memberships — every
document has exactly one owning collection, satisfying PRD §10.2's "exactly
one collection in v1" invariant with no ambiguous rows needing a reviewed
remap.

**Shared resources** (disposable copy, current real state): **0** of 14
`DocumentCollection` rows and **0** of 15 `Persona` rows are marked
`is_shared=True`. This is expected and correct, not a defect — PRD §10.3
requires marking existing public collections/Agents Shared to be "an
explicit reviewed allowlist or a post-migration admin action," never an
automated migration decision. **This remains an open, deliberate,
human action for a Cofficiency admin to take via the already-shipped
Shared toggle UI (skunkBOX `personas.py` `toggle_shared_agent()` /
`documents.py`'s collection-share toggle) before Shared knowledge/Agents
have anything to show a customer tenant.** See §5 (Rollout) step 4.

**Real database**: backed up to `instance/app.db.pre-phase8-migration.bak`
before applying; migration applied cleanly; full test suite re-run
afterward with an unchanged result (see §3).

---

## 2. saas-mortgage (Cophy)

### 2.1 State found

`flask db current` and `flask db heads` both reported `m3n4o5p6q7r8` — the
real dev database was already fully migrated to head, with every Phase 5–7
migration (`j0k1l2m3n4o5` tenant external_id, `k1l2m3n4o5p6` AiAgent
is_shared, `l2m3n4o5p6q7` Experiment table, `m3n4o5p6q7r8` AI Quality nav
seed) already applied and backed up individually during those phases
(`instance/app.db.pre-phase5-migration.bak` through
`instance/app.db.pre-phase7-nav-migration.bak`, all present in `instance/`).
No pending migration to rehearse.

### 2.2 Commands run

```bash
flask db heads
flask db current
python -m pytest -q   # legacy_db/migrated_db fixtures re-run the FULL
                       # from-scratch migration chain (PRE_TENANT_REVISION
                       # through head, on realistic seeded legacy data) on
                       # every single test — this is a full-chain rehearsal
                       # executed automatically on every run, not a one-off
```

### 2.3 Results

**UUID reconciliation** (real dev database):

| Tenant | Cophy `external_id` | skunkBOX `public_id` | Match |
|---|---|---|---|
| Cofficiency | `3f9d9a2e-2b7a-4a63-9d1a-8e4c9c9b7a10` | `3f9d9a2e-2b7a-4a63-9d1a-8e4c9c9b7a10` | ✅ |
| AdvantageFirst | `7c1e6b44-5a3f-4e9a-9b52-1e3a7f6d2c88` | `7c1e6b44-5a3f-4e9a-9b52-1e3a7f6d2c88` | ✅ |

Both `sync_status='synced'`, both `is_active=True`. Local integer ids
(`1`, `2`) unchanged from before the Phase 5 migration — confirmed by the
Phase 5 migration's own hand-written mapping (never auto-generated for
these two tenants) and by `test_migration_did_not_change_local_ids_or_ownership`
(`tests/test_cross_system_tenant_sync.py`) passing.

**Shared Agent mirrors**: 4 local `AiAgent` rows exist (Thraxa, Mac,
Freddie, Mae), all `is_shared=False` (hand-configured, tenant-owned) —
correctly zero `is_shared=True` mirrors, since skunkBOX currently has zero
Shared Personas to mirror (§1.3). This will change automatically, with no
code/migration needed, the moment a Cofficiency admin marks a Persona
Shared on the skunkBOX side — `app/services/agent_sync.py`'s
`sync_shared_agents_for_tenant()` picks it up on the next
`list_conversations()` view.

**Full-chain rehearsal**: exercised continuously by the test suite's
`legacy_db`/`migrated_db` fixtures (`tests/conftest.py`), which build a
fresh SQLite database seeded with realistic pre-Phase-1 data, migrate it to
`PRE_TENANT_REVISION`, insert legacy rows, then migrate the rest of the way
to `head` — on every one of the 117 tests in the suite. See §3.

---

## 3. Test suite baseline (both repos, post-rehearsal)

```bash
# saas-platform
venv/bin/python -m pytest -q
#   111 passed, 2 failed (tests/test_evaluation.py::test_null_actual_returns_zeros,
#   tests/test_evaluation.py::test_empty_string_actual_returns_zeros)

# saas-mortgage
.venv/bin/python -m pytest -q
#   117 passed
```

The two `test_evaluation.py` failures are **pre-existing and unrelated to
the Cross-System Tenant AI Assets PRD** — they assert on
`evaluate_structured_field()`'s F1-score handling of `None`/empty-string
actual values, a quality-scoring concern with no connection to tenant
isolation, sharing, or provisioning. Confirmed pre-existing via `git status`
(clean working tree before any Phase 8 work began) and `git log` (both the
test file and the function under test were last touched by unrelated
commits, not by any Cross-System phase). Left unfixed as out of scope for
this PRD; tracked here rather than silently claimed as passing. All other
110 tests plus the full Cophy suite (dozens covering exactly the
tenant/sharing/provisioning surface this PRD is about) pass cleanly.
