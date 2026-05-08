# Changelog

## [2026-05-07] - Learning Center

### Feature
- Added **Learning Center** tab to the AI Agents section (alongside Conversations)
- New routes in `agents.py`: `learning_center()` and `learning_center_doc(doc_id)`
- `_get_docs_integration()` — finds the active integration with `use_case = "Documents"`
- `_call_skunkbox_get()` — generic GET helper to skunkBOX API (same URL normalisation as chat)
- **List view** (`/agents/learning-center`): document table with file-type icon, title, collection, type badge, status badge, pages, upload date; pagination at 25/page with smart page-number range
- **Detail view** (`/agents/learning-center/<doc_id>`): two-column layout — preview panel (text `content_preview`, PDF iframe, image, or "no preview" fallback) + full metadata panel showing all fields returned by the API (known fields with friendly labels first, then any extras auto-labelled from the key name)
- Empty state if no Documents integration is configured, with link to External APIs config
- Sidebar AI Agents nav link stays highlighted on both Learning Center routes

## [2026-05-07] - Integration Use Case field

### Feature
- Added `use_case` column to `Integration` model (`String(40)`, default `"AI Agents"`)
- Added Alembic migration `c2d3e4f5g6h7_add_integration_use_case.py` (chains off `b1c2d3e4f5g6`)
- Add / Edit Integration modals now include a required **Use Case** dropdown with two options: `AI Agents` and `Documents`
- Use Case displayed as a colour-coded badge in the External APIs table (green for AI Agents, purple for Documents)
- Routes `add_integration` and `save_integration` in `models.py` now read and persist `use_case`

## [2026-05-07] - Activity logging for conversations, user management, system config

### Activity logging
- Added `log_activity` calls to `app/routes/users.py`: user created, updated, password changed, activated, deactivated
- Added `log_activity` calls to `app/routes/agents.py`: conversation started, archived
- Added `log_activity` calls to `app/routes/models.py`: LLM model created/updated/activated/deactivated, integration created/updated, AI agent created/updated/activated/deactivated, attributes saved
- Expanded `ACTION_LABELS` in `app/activity_logger.py` to cover all new action keys

## [2026-05-07] - Attributes Edit button fix

### Bug fix
- Fixed broken Edit button in System Config > Attributes: `{{ category | tojson }}` inside a double-quoted `onclick="..."` attribute produced unescaped `"` characters that truncated the HTML attribute value, silently breaking the JS call. Changed attribute delimiter to single quotes: `onclick='openAttrModal({{ category | tojson }})'`
- Removed stale inner `tax-tabs` strip from the Attributes section (leftover from before the 4-tab top-level strip was added)
- Removed stale Jinja `{% if can_view_models or can_view_integrations %}style="display:none"{% endif %}` from `config-tab-attributes` div — show/hide is now handled entirely by `switchTopTab()` JS, consistent with all other sections

## [2026-05-07] - AI Agents feature + UI polish

### AI Agents feature
- Added `AiAgent`, `AgentConversation`, `AgentMessage` models to `app/models.py`
- Added Alembic migration `b1c2d3e4f5g6_add_ai_agents.py` (chains off `a1b2c3d4e5f6`)
- Added `agents` page slug to `page_registry.py`; seeded into all existing roles on startup
- Added `AGENT_AVATAR_UPLOAD_FOLDER` config key; directory created on app startup
- Added `agents_bp` blueprint (`app/routes/agents.py`) with routes: list conversations, new conversation, view conversation, send message (AJAX → skunkBOX API), archive conversation
- skunkBOX API call: `POST {base_url}/api/v1/chat/messages` with `X-API-Key` header, `persona_id` / `message` / `session_id` body; `skunkbox_session_id` persisted for thread continuity
- Added `app/templates/agents/list.html` — conversations list with "New Conversation" agent-picker overlay
- Added `app/templates/agents/conversation.html` — chat UI with auto-grow textarea, Enter-to-send, `marked.js` markdown rendering, typing indicator animation
- Added AI Agents CRUD to `app/routes/models.py`: `add_agent`, `save_agent`, `toggle_agent` with avatar file upload
- Added "AI Agents Config" tab to System Config (`models/list.html`) — agent table with avatar, integration reference, skunkBOX Agent ID; add/edit modals with file upload
- Added `robot`, `message`, `send` icons to `macros/ui.html`
- Added `requests==2.32.3` to `requirements.txt`

### Navigation changes
- "AI Agents" sidebar section moved to sit directly below Dashboard, above Administration
- "Configure Agents" removed as a standalone nav item — accessible only as a tab within System Config
- System Config now defaults to AI Agents Config tab (no hash or `#agents`); `#integrations` and `#attributes` still navigate directly to their sections

### UI polish
- Breadcrumb separator changed from `>>` to ` > `
- Added chat bubble CSS to `style.css`: user/agent bubble layout, markdown-in-bubble styles, typing dots bounce animation

## [2026-05-06] - Documentation + sidebar + LLM Models UI

### Documentation restructure
- Split help section into two pages: User Guides (Release Notes, Quick Start, User Manual) and System Overview (Architecture, Python Dependencies)
- Added `sb-page-header` with title and description below tab strip on each doc page
- Added three-level breadcrumbs to all documentation pages
- Stripped leading `# H1` from markdown files in `_render_doc()` to prevent duplicate headers
- Added `md` Jinja2 template filter for markdown → HTML conversion

### Release Notes
- Switched to three-tier card pattern: Major (green), Minor (blue), Patch (grey)
- Card UI uses CSS variables for full dark-mode support

### Sidebar collapse
- Sidebar collapses/expands by clicking the brand mark; state persisted in `localStorage`
- Section labels replaced by gray separator lines in collapsed state
- Nav labels hidden in collapsed state; icon position unchanged
- Floating tooltip shown on icon hover when sidebar is collapsed

### LLM Models table
- Status badges: `badge-active` (green), `badge-inactive` (red), `badge-default` (purple)
- Deactivate/Reactivate via global `confirmAction` modal added to `base.html` (Escape key supported)

## [2026-05-06] - Initial cleanup — align with skunkBOX principles

- Removed unauthenticated `/bootstrap/reset-admin` endpoint (security hole)
- Fixed deprecated SQLAlchemy patterns: `Model.query.get()` → `db.session.get()`, `get_or_404()` → `db.get_or_404()`
- Added `is_admin()` method to User model — use instead of `role == "admin"` string comparison
- Added `updated_at` column to User, Role, and LlmModel models
- Added `last_login` column to User model; populated on successful login
- Initialized Flask-Migrate; created initial schema migration (`db2364c230d4`)
- Removed `db.create_all()` from app factory — schema now managed via migrations
- Added schema guard to `_seed_defaults()` so it skips gracefully before `flask db upgrade` is run
- Extracted shared permission helper `user_has_access()` to `app/access.py` — eliminates duplicate logic in models route and `__init__.py` context processor
- Passed `PAGES` from routes to templates — no more hardcoded page lists in Jinja
- Added `.local-time` UTC→local timestamp conversion pattern to all templates (matches skunkBOX convention)
- Added UTC→local JS handler to `app.js`
- Created `CLAUDE.md` with project conventions aligned with skunkBOX
- Fixed `DESIGN_SYSTEM.md` — CSS variable names now match the actual `style.css`
