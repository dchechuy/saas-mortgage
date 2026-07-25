# saas-mortgage — Development Guidelines

This file is read by Claude (and any AI coding assistant) at the start of every session.
Follow these conventions exactly. When in doubt, check how skunkBOX does it — this project mirrors those patterns.

---

## Project Overview

`saas-mortgage` is a reusable Flask SaaS foundation. Its purpose is to be copied and renamed at the start of every new prototype, providing a working admin shell (auth, users, roles, permissions, config, help) without any domain-specific features.

**Local:** `~/Workspace/saas-mortgage`
**Stack:** Python Flask · Jinja2 · SQLite (SQLAlchemy) · Flask-Migrate · Fernet encryption

---

## First Run (new clone or fresh instance)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — set SECRET_KEY and ENCRYPTION_KEY at minimum
flask db upgrade          # creates all tables; also seeds the Cofficiency
                          # and AdvantageFirst tenants (see "Tenants" below)
python run.py             # seeds defaults on first startup, then serves on :5011
```

Default admin: `admin` / `Changeme-123` (forced password change on first login), home tenant Cofficiency, remembered active tenant AdvantageFirst.

### Tenants

The app is multi-tenant (see `docs/ARCHITECTURE.md` § Tenant isolation and
`docs/prompts/Tenant Separation - PRD.md`). `flask db upgrade` seeds exactly
two tenants on a fresh database: the protected `cofficiency` tenant and an
`advantagefirst` tenant that owns all pre-existing sample/business data.
Never create a real customer tenant until you've run every tenant-separation
migration — check `flask db current` against the latest revision first.

---

## Database Conventions

- **Table names:** Singular always — `user`, `role`, `permission`, not `users`
- **FK naming:** `{table_name}_id` e.g. `role_id`, `user_id`
- **Soft delete:** Use `is_active` flag — never hard-delete users or config records
- **Timestamps:** Every mutable model must have `created_at` AND `updated_at`
  ```python
  created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
  updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
  ```
- **After every models.py change:** run migrations before committing
  ```bash
  flask db migrate -m "describe what changed"
  flask db upgrade
  git add migrations/
  ```

---

## Encryption

API keys and secrets are stored encrypted using Fernet symmetric encryption.

```python
from app.crypto import encrypt_value, decrypt_value

# Before saving to DB
record.api_key_encrypted = encrypt_value(plain_key)

# Before using
plain_key = decrypt_value(record.api_key_encrypted)
```

`ENCRYPTION_KEY` is set in `.env`. If not set, falls back to `SECRET_KEY` (acceptable in dev, not in prod).
Never log or return `plain_key` in any response or template.

---

## Permissions System

Routes are protected with the `@permission_required` decorator from `app/access.py`:

```python
from app.access import permission_required

@bp.route('/something')
@login_required
@permission_required('page_slug', 'view')   # or 'edit'
def my_view():
    ...
```

For multi-section pages that need to check multiple slugs without blocking access, use `user_has_access()`:

```python
from app.access import user_has_access

can_view = user_has_access('models', 'view')
```

Admin role bypasses all permission checks automatically.

To add a new page to the permission system: add it to `PAGES` in `app/page_registry.py`. That is the single source of truth — templates receive `pages` from the route context.

---

## User Model Helpers

```python
# Check if admin — always use the method, not string comparison
if current_user.is_admin():
    ...

# Never do this:
if current_user.role == "admin":   # wrong — use is_admin() instead
    ...
```

---

## CSS Conventions

Always use CSS variables — never hardcode colors. This is what enables dark mode.

```css
/* Correct */
color: var(--text);
background: var(--panel);
border: 1px solid var(--border);

/* Wrong — breaks dark mode */
color: #333;
background: #fff;
```

See `app/static/css/style.css` for all available variables. See `docs/DESIGN_SYSTEM.md` for usage guidance.

---

## Templates

### Breadcrumbs
Every route must pass breadcrumbs:
```python
breadcrumbs=[
    {"label": "Home", "url": url_for("main.dashboard")},
    {"label": "Page Name", "url": None},
]
```

### Flash messages
```python
flash("Success message", "success")
flash("Error message", "error")
flash("Warning message", "warning")
```

### UTC timestamps
Always wrap timestamps with `.local-time` so JavaScript converts them to the user's timezone:
```jinja2
<span class="local-time" data-utc="{{ record.created_at.isoformat() }}">
  {{ record.created_at.strftime('%Y-%m-%d') }}
</span>
```

### Jinja None guards
```jinja2
{{ (record.title or '(untitled)') | truncate(80) }}
```

---

## SQLAlchemy Patterns

Use the modern style — never the deprecated `Model.query.get()`:

```python
# Correct
user = db.session.get(User, user_id)           # returns None if not found
user = db.get_or_404(User, user_id)            # returns 404 if not found

# Deprecated — do not use
user = User.query.get(user_id)                 # removed in SQLAlchemy 2.x
user = User.query.get_or_404(user_id)          # removed in SQLAlchemy 2.x
```

---

## Seeding

`_seed_defaults()` in `app/__init__.py` runs on every startup but is guarded — it silently skips if the schema isn't up to date. After `flask db upgrade`, it seeds admin user, default roles, attributes, and integrations on the next startup automatically.

Do not add large data loads to `_seed_defaults()` — keep it to structural defaults only.

---

## Git Workflow

```bash
# Save and deploy
git add -A && git commit -m "brief description"
git push

# After every session, append to CHANGELOG.md:
## [YYYY-MM-DD] - brief description
- Change 1
- Change 2
```

---

## Naming in UI

| Element | Convention | Example |
|---|---|---|
| Nav section labels | ALL CAPS | `ADMINISTRATION` |
| Nav links | Title Case | `User Management` |
| Page headers | Title Case | `Roles & Permissions` |
| Button labels | Title Case | `Add User`, `Save Role` |
| Form labels | Title Case | `Role Name`, `API Key` |
| Status badges | Title Case | `Active`, `Minor Release` |

---

## Starting a New Project from This Template

1. Copy the folder: `cp -r saas-mortgage my-new-project`
2. Create a new GitHub repo and push
3. Update `CLAUDE.md` with the new project name and purpose
4. Rename the `deploy/saas-mortgage.service` systemd file
5. Search-replace `saas-mortgage` in templates and config
6. Run `flask db upgrade` on the new instance
7. Start adding domain-specific models, routes, and templates

---

## After This Session
Append a summary of changes to `CHANGELOG.md`.
