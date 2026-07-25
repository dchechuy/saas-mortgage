# Phase 4 — Tenant-Isolated Configuration and Feature Flags

You are working on `saas-mortgage` (Cophy Portal).

Read:

- `docs/prompts/Tenant Separation - PRD.md`
- Completed Phases 1–3
- `app/routes/models.py`, its templates, feature-flag injection, and navigation injection
- Any repository agent instructions

Implement only Phase 4.

---

## Goal

Tenant-isolate LLM models, attributes, integrations/API keys, and AI agents. Implement per-tenant feature overrides while preserving explicitly global configuration.

---

## Tenant-owned configuration

Scope these models to `active_tenant.id` in every list, create, update, toggle, and bulk operation:

- `LlmModel`
- `Attribute`
- `Integration`
- `AiAgent`

Rules:

- Creation sets tenant from server context.
- Direct ID routes reject cross-tenant records.
- Duplicate checks include active tenant.
- Default LLM model changes affect only active tenant.
- Attribute batch update/delete includes active tenant in every lookup and predicate.
- Integration/API-key screens never reveal another tenant's metadata or encrypted-secret presence.
- AI-agent integration choices contain only active-tenant integrations.
- Creating/updating an agent rejects an integration belonging to another tenant.
- Deactivating an agent archives only that same tenant agent's conversations.
- Any uploaded agent-avatar naming/storage behavior must not make cross-tenant access possible.

Search for configuration queries outside `routes/models.py`, including document generation and agent execution, and update them when they represent tenant-owned selection.

---

## Per-tenant feature flags

Keep `FeatureFlag` as global catalogue/default. Use `TenantFeatureFlag` for active-tenant overrides.

Implement one shared resolver, for example:

```python
is_feature_enabled(key, tenant=None) -> bool
effective_feature_flags(tenant=None) -> dict[str, bool]
```

Resolution:

1. Active tenant override when present.
2. Otherwise global `FeatureFlag.is_enabled`.
3. Existing defaults remain enabled.

Update:

- Template feature-flag injection
- Navigation injection
- Feature-flags System Config tab
- Toggle/update route
- Any route-level feature checks

The UI edits the active tenant's override, not the global catalogue. A new tenant needs no override rows.

Show enough context in the flags UI to make clear which tenant is being configured. If practical, distinguish inherited from explicitly overridden state and offer “reset to global default”; otherwise document that enhancement and ensure effective state is correct.

A disabled feature must not remain callable merely because its navigation item is hidden. Add a reusable route guard or equivalent server-side enforcement for flagged surfaces.

---

## Keep these global

Do not tenant-scope:

- `Role`
- `Permission`
- `ReleaseNote`
- `NavSection`
- `NavItem`
- `DocPrompt`
- Feature flag catalogue rows themselves

Sections/navigation layout and documentation prompts remain globally editable under existing authorization. Make the UI wording clear where a System Config tab is global versus active-tenant-specific if ambiguity would cause an administrator to make unsafe assumptions.

---

## Interim skunkBOX boundary

No skunkBOX API contract change occurs in this phase.

Isolation is indirect:

- Each tenant has separate integrations/API keys.
- Each tenant's agents reference only its integrations.
- Later phases ensure conversations and Learning Center calls can use only those agents.

Do not add a speculative tenant header/body field to skunkBOX calls yet.

---

## Tests

Cover:

1. Same model/attribute/integration name is allowed in different tenants.
2. Duplicate within one tenant is rejected.
3. Lists expose only active-tenant records.
4. Creates bind active tenant despite forged input.
5. Cross-tenant update/toggle/delete/batch IDs are rejected.
6. Default-model updates do not affect another tenant.
7. Agent cannot reference another tenant's integration.
8. Agent deactivation cannot archive another tenant's conversations.
9. Feature state inherits enabled global default.
10. Tenant override changes only selected tenant.
11. Navigation and direct route behavior use the same effective flag state.
12. Global roles, navigation layout, release notes, and doc prompts remain global.

Run the full available test suite.

---

## Deliverables

- Tenant-scoped configuration routes/templates
- Cross-tenant relationship validation
- Effective feature-flag service and per-tenant UI
- Route-level disabled-feature enforcement
- Tests
