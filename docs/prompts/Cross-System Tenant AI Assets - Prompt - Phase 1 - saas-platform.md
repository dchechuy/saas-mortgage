# Phase 1 — skunkBOX Tenant Registry and Migration

You are working on `saas-platform` (skunkBOX).

Read:

- `saas-mortgage/docs/prompts/Cross-System Tenant AI Assets - PRD.md`
- `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, and `docs/CONVENTIONS.md`
- Existing Users & Config routes/templates, API-key models/authentication, logs, and migrations

Implement only Phase 1.

---

## Goal

Create the authoritative skunkBOX tenant registry, migrate all existing skunkBOX records to Cofficiency, add the Tenants administrative tab as tab 3 under Users & Config, and establish tenant ownership on API keys/logs.

No existing skunkBOX record belongs to AdvantageFirst.

---

## Schema

Add `Tenant` with immutable UUID `public_id`, name, slug, active/protected state, and timestamps as specified in the PRD.

Seed:

- Cofficiency: protected and active
- AdvantageFirst: active

Add required tenant ownership foundation to:

- `SkunkApiKey`
- API request logs
- LLM/request/activity logs where the event can represent tenant work
- Conversations/sessions/attachments created through tenant API keys where appropriate

Inventory every major tenant-owned model named in the PRD. In this phase, add/backfill ownership broadly when safe, but leave route-wide Component/knowledge/quality enforcement to Phases 2 and 3.

Use explicit model relationships and indexes. API/event history stores tenant at event time rather than inferring it later from a mutable relationship.

---

## Migration

Create a hand-reviewed Alembic migration:

1. Create Tenant.
2. Insert Cofficiency and AdvantageFirst with generated, stable UUID values embedded in the migration.
3. Add ownership columns nullable.
4. Backfill every existing skunkBOX row to Cofficiency.
5. Backfill all existing API keys to Cofficiency.
6. Backfill every historical log to Cofficiency.
7. Add constraints/indexes and make required columns non-null.
8. Preserve all record counts and relationships.

Do not mark collections or Personas Shared in this phase. They default private. Do not assign anything to AdvantageFirst.

Include migration verification output/tests listing counts by model before and after. Stop rather than silently losing data on an unexpected schema/cardinality condition.

---

## Tenant administration UI

Add **Tenants** as tab 3 under **Users & Config**. Shift subsequent tabs without changing their behavior.

Only Cofficiency administrators may:

- List tenants
- Create
- Edit safe metadata
- Archive/reactivate non-protected tenants

Display stable UUID and useful owned-resource counts. Cofficiency cannot be renamed, re-slugged, or archived. Do not hard-delete.

Tenant lifecycle actions must be logged.

---

## API authentication foundation

Bind every `SkunkApiKey` to one tenant. Update `require_api_key` to resolve `g.tenant`.

In this phase:

- Reject keys for inactive tenants.
- Make an asserted tenant UUID optional and consistency-only; reject mismatch.
- Add tenant ID to API log writes.
- Keep existing allowlists as additional restrictions.
- Do not add customer management APIs yet.

---

## Tests

Cover:

- Seeded/protected tenants
- Stable unique UUIDs
- All legacy data Cofficiency-owned
- AdvantageFirst owns no migrated records
- API-key tenant resolution and inactive-tenant rejection
- Asserted tenant mismatch rejection
- Event-time tenant logging
- Tenant tab order and authorization
- Protected tenant restrictions
- Upgrade/downgrade/upgrade on disposable data

Run the full suite and repository-required migration commands. Update `CHANGELOG.md` per repository instructions.

---

## Deliverables

- Models and migration
- Users & Config Tenants tab
- API-key/log tenant foundation
- Migration and authorization tests
- Updated architecture notes and changelog

