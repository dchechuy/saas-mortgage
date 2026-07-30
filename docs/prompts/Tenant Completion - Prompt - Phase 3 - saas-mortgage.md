# Phase 3 — Client Portal CSRF Protection

**Target system:** `saas-mortgage`  
**Product name:** Cophy Portal / Client Portal  
**System role:** Customer-facing portal with local users, tenant switching, reporting, and customer UI

Do not implement this phase in `saas-platform` (skunkBOX).

Read:

- `docs/TENANT_ISOLATION_AUDIT.md`
- All POST/PUT/PATCH/DELETE routes and forms
- Login, tenant switching, user management, System Config, conversations, AI Quality, and tenant lifecycle proxy routes

---

## Goal

Add repository-wide CSRF protection. The existing tenant switch route and all other form mutations currently follow a project convention that has no CSRF middleware.

This must be a complete portal-wide change, not a one-off token only on the tenant switcher.

---

## Requirements

- Use a maintained Flask-compatible CSRF implementation.
- Initialize protection centrally in the application factory.
- Add tokens to every server-rendered mutation form.
- Protect AJAX/JSON mutations with a token header or documented equivalent.
- Update shared form macros/helpers to reduce duplication.
- Preserve file uploads and asynchronous chat/quality flows.
- Return safe, user-friendly failures for expired/missing tokens.
- Do not include secrets or tenant identifiers in CSRF tokens.
- Login CSRF protection must not create a redirect loop.

Inventory all mutation endpoints, including:

- Authentication/logout/password
- Tenant switch/create/edit/archive/reactivate/sync
- User and avatar management
- Roles/permissions
- Feature flags
- Models/attributes/integrations/Agents
- Conversations/favorites/archive/attachments
- Document and Agent proxy mutations
- Components/Datasets/Experiments
- Release/documentation administration

Explicitly exempt only endpoints that have a separate authenticated machine-to-machine scheme and cannot be called with a browser session. Document every exemption.

---

## Tenant-specific security tests

Cover:

1. Tenant switch fails without/with invalid token.
2. Cross-site form cannot create a user under the active tenant.
3. Cross-site form cannot archive a tenant or alter feature flags.
4. AJAX conversation/quality mutations succeed with valid header token.
5. Token protection does not replace tenant ownership checks.
6. Tokens remain valid across ordinary active-tenant switching as intended.
7. Login/logout/password and file-upload flows remain functional.

Run the complete test suite and update templates, tests, dependencies, architecture, user-facing error handling, and the known-gap section of `docs/TENANT_ISOLATION_AUDIT.md`.

