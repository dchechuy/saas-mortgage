# Phase 2 — Active Tenant Context, Tenant Administration, and Switcher

You are working on `saas-mortgage` (Cophy Portal).

Read:

- `docs/prompts/Tenant Separation - PRD.md`
- The completed Phase 1 implementation and migration
- `docs/ARCHITECTURE.md`
- Any repository agent instructions

Implement only Phase 2. Preserve Phase 1 migration semantics.

---

## Goal

Add a single server-side active-tenant resolver, Cofficiency-only workspace switching, last-used persistence, tenant administration, and event-time tenant attribution.

---

## Central tenant context

Create a focused module such as `app/tenant_context.py` with well-tested helpers:

```python
is_cofficiency_user(user) -> bool
get_cofficiency_tenant() -> Tenant
get_active_tenant(user=None) -> Tenant
get_active_tenant_id(user=None) -> int
can_switch_tenants(user=None) -> bool
require_tenant_record(record) -> None
```

Required resolution:

- Unauthenticated requests have no active tenant.
- External users always resolve to their immutable home tenant.
- Cofficiency users resolve to `last_active_tenant_id` when it references an active tenant.
- Invalid, missing, or inactive remembered tenants fall back to Cofficiency.
- Never trust a tenant ID from session/request as authorization.
- Avoid silently querying a tenant on every template expression; resolve once per request where practical.

Expose `active_tenant`, `can_switch_tenants`, and the tenant list needed by the header through a context processor. Do not expose inactive tenants in the switcher.

---

## Tenant switch endpoint

Add a POST-only route, for example:

```text
POST /tenants/switch
```

Behavior:

- Login required.
- Only Cofficiency users may switch.
- Accept only an existing active tenant.
- Persist `current_user.last_active_tenant_id`.
- Record `tenant.switched`, attributed to the destination tenant.
- Redirect back only to a safe local path; otherwise use a known internal default.
- Follow the application's CSRF conventions.
- External users receive 403 or an equivalent safe rejection.

Do not modify `current_user.tenant_id`.

---

## Header switcher

In the shared header:

- Place the tenant switcher immediately to the left of the upper-right user avatar.
- Show it only to Cofficiency users.
- Display the active tenant name.
- Provide all active tenants in a compact dropdown.
- Clearly mark the current selection.
- Preserve the existing header layout at supported responsive widths.
- External users see no empty placeholder.

Switching tenant must not imply elevated permissions; existing navigation/permissions remain authoritative.

---

## Tenant administration

Add Cofficiency-administrator-only tenant management:

- List active and archived tenants.
- Create a tenant from a required name.
- Generate a normalized unique slug at creation.
- Permit safe metadata edits.
- Archive/reactivate non-protected tenants.
- Never hard-delete in v1.
- Never rename, re-slug, or archive the protected Cofficiency tenant.
- Prevent creation of case-insensitive name/slug duplicates.
- Do not allow archived tenants to receive new records.

Place tenant management in a sensible existing administrative area or add a small dedicated page and navigation entry consistent with the current page registry and permission system. Reuse the global admin role; do not introduce tenant-specific roles.

---

## Activity attribution

Update `log_activity()` so new rows always receive the resolved active tenant ID.

Important:

- Actor identity and tenant context are separate.
- A Cofficiency actor working in AdvantageFirst logs activity under AdvantageFirst.
- External activity logs under the user's home tenant.
- Login resolves the user's remembered/home tenant after authentication and logs there.
- A switch event logs under the destination tenant.
- Logging must remain fail-safe without hiding normal application errors.

Update other log writers/helpers that can safely take active tenant context in this phase. Do not complete reporting UI filtering yet; that belongs to Phase 6.

---

## Tests

Cover at minimum:

1. External user active tenant equals home tenant.
2. External user cannot switch, including a forged POST.
3. Cofficiency user defaults correctly when remembered tenant is null/invalid/inactive.
4. Cofficiency user can switch to an active tenant.
5. Switch persists across a new session/login.
6. Switch does not mutate home tenant.
7. Header switcher visibility and active label are correct.
8. Existing role permissions still hide unauthorized pages after switching.
9. Cofficiency admin can create/archive/reactivate a customer tenant.
10. Protected Cofficiency cannot be renamed or archived.
11. Activity by a Cofficiency user is recorded under selected tenant.
12. Historical data from Phase 1 remains unchanged.

Run the full available test suite.

---

## Deliverables

- Central tenant-context module
- Context processor integration
- Switch route and header UI
- Tenant administration UI/routes
- Active-tenant activity attribution
- Tests

Do not yet claim full tenant isolation for user lists, configuration, conversations, dashboards, or reporting. Those follow in later phases.
