# Phase 3 — Tenant-Isolated User Management

You are working on `saas-mortgage` (Cophy Portal).

Read:

- `docs/prompts/Tenant Separation - PRD.md`
- Completed Phases 1 and 2
- Existing user routes/templates and permission helpers
- Any repository agent instructions

Implement only Phase 3.

---

## Goal

Make user management fully tenant-safe while preserving global login identities and global role templates.

---

## Required behavior

### User list

- Filter `User` by `active_tenant.id`.
- Sort as before.
- Role counts include only active users in the active tenant.
- Role dropdown/options still come from global `Role` records.
- Cofficiency active tenant shows only Cofficiency users.
- AdvantageFirst active tenant shows only AdvantageFirst users, including when viewed by a Cofficiency user.
- An external user never sees another tenant's users.

### Add user

- Assign `tenant_id` from the server-resolved active tenant.
- Do not accept `tenant_id` from form/JSON/query parameters.
- Do not show a tenant selector.
- Require the active tenant to be active.
- Keep username and email globally unique.
- Preserve existing role validation and password behavior.
- Log creation under the active tenant.

### Edit, toggle, and avatar operations

Every route accepting `user_id` must verify that the target user's home tenant equals the active tenant before reading or mutating it:

- Edit user
- Activate/deactivate user
- Admin avatar upload
- Any newly discovered user-specific route

Prefer a 404 for a cross-tenant target. Apply the check before rendering data or processing form fields.

Self-service operations such as password change and self-avatar upload remain available to the authenticated user, but must not permit tenant mutation.

### Immutable home tenant

- Do not render an editable tenant field.
- Ignore/reject forged tenant fields.
- No route may update `User.tenant_id`.
- Add a clear read-only tenant label to the edit screen if useful.
- Document that corrections require a future controlled migration, not ordinary UI.

### Cofficiency semantics

- Cofficiency users may create users in whichever active tenant they selected, subject to existing edit permission.
- Creating a user in a customer tenant does not make that user internal.
- Creating a user while Cofficiency is active creates a Cofficiency/internal user.
- A Cofficiency actor remains assigned to Cofficiency while managing customer users.

---

## Security audit

Search all `User.query`, `db.session.get(User, ...)`, and `db.get_or_404(User, ...)` call sites.

Classify each as:

- Tenant-scoped operational/user management
- Global authentication identity lookup
- Global relationship lookup needed for display

Apply active-tenant filtering to the first category without breaking login. Do not globally override `User.query`, because authentication must locate a user before tenant context exists.

Ensure conversation user filters are not addressed incompletely here; record them for Phase 5.

---

## Tests

Use at least three tenants/users: Cofficiency internal, AdvantageFirst external, and another customer tenant.

Cover:

1. User lists and counts are tenant-isolated.
2. Cofficiency tenant lists only Cofficiency users.
3. Cofficiency user switching to customer A sees customer A users.
4. External user sees only home-tenant users.
5. Added user receives active tenant automatically.
6. Forged `tenant_id` cannot alter assignment.
7. Existing user's tenant cannot be changed.
8. Cross-tenant edit/toggle/avatar IDs are rejected.
9. Global username/email uniqueness still applies.
10. Global roles remain selectable according to existing permissions.
11. Activity rows use active tenant while actor remains Cofficiency.

Run the full available test suite.

---

## Deliverables

- Tenant-safe user routes and templates
- Immutable assignment enforcement
- User-query audit notes in the implementation summary
- Regression/security tests
