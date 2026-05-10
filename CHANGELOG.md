# Changelog

## [2026-05-10] - Doc Prompt Editor Phase 1: editable help-doc prompts with AI-assisted improve flow
- app/models.py: added DocPrompt model (key, label, prompt_text, timestamps)
- migrations/versions/1bdbff5ce391: creates doc_prompt table
- app/doc_generator.py: replaced _SYSTEM_PROMPT constant with DEFAULT_PROMPTS dict; added _get_doc_prompt() DB-backed helper; simplified three generators to use _get_doc_prompt()
- app/__init__.py: imports DocPrompt; table guard added; seeds four default prompts on startup
- app/routes/models.py: added DocPrompt import; list_models() passes doc_prompts + default_prompts to template; added save_doc_prompt and reset_doc_prompt routes
- app/routes/help.py: added log_activity import; added improve_doc_prompt (POST /help/improve/<doc_key>) and apply_improved_prompt (POST /help/improve/<doc_key>/apply) routes for AI-assisted prompt editing
- app/templates/models/list.html: added "Help Prompts" tab with editable textarea + Save/Reset per prompt
- app/templates/help/doc_page.html: added "Improve this doc" button and three-step modal (instruction → AI review → apply/regenerate)

## [2026-05-10] - Fix Generate Release Notes: always shows only new entries
- app/models.py: added changelog_snapshot (TEXT) column to ReleaseNote
- app/routes/help.py: generate_release() saves CHANGELOG.md text snapshot at publish time
- app/routes/help.py: changelog_preview() diffs against snapshot instead of git commit hash
- migrations/versions/b543b16784f2: adds column + backfills v1.0.0 snapshot so next generation shows only post-v1.0.0 entries

## [2026-05-10] - My Conversations: agent tiles become a ribbon on overflow
- app/templates/agents/list.html: tiles stay full-size (268×303px); overflow:hidden + translateX ribbon with ‹ › arrows activates only when tiles exceed available width
- app/templates/agents/list.html: arrows hidden when all tiles fit; re-evaluated on window resize

## [2026-05-10] - Allow sending attachment-only messages (no text required)
- app/routes/agents.py: removed hard "message is empty" block when attachment_ids are present
- app/routes/agents.py: skunkBOX receives "[File attached — please review]" placeholder when content is empty
- app/routes/agents.py: conversation auto-title falls back to attachment filename when no text

## [2026-05-10] - New Conversation modal: ribbon picker, wider, auto-select
- app/templates/agents/list.html: modal is 25% wider (780→975px)
- app/templates/agents/list.html: agent picker replaced with horizontal ribbon with left/right arrows; agents already sorted by last-use from route
- app/templates/agents/list.html: first agent auto-selected on modal open; arrows hidden when all tiles fit

## [2026-05-10] - New Conversation modal: attachment support
- app/routes/agents.py: new_conversation() returns JSON when X-Requested-With: XMLHttpRequest so modal can get conv_id before navigating
- app/templates/agents/list.html: added paperclip button, file input, attachment chips, and async submitNewConv() that creates conv then uploads files
- app/templates/agents/conversation.html: auto-send IIFE now restores staged modal attachments from sessionStorage before sending the first message

## [2026-05-09] - Conversation attachments — historical chips & dynamic bubble chips (Phase 5)
- app/templates/agents/conversation.html: added Jinja2 attachment chips above message text for both user and assistant historical bubbles
- app/templates/agents/conversation.html: added CSS .attach-chip-history with hover state for download links
- app/templates/agents/conversation.html: added buildAttachmentChipsHtml() JS helper for dynamic bubble chips
- app/templates/agents/conversation.html: appendUserBubble() now accepts attachments arg and prepends chips HTML
- app/templates/agents/conversation.html: sendMessage() captures sentAttachments before clearing pendingAttachments and passes to appendUserBubble()
- app/routes/agents.py: view_conversation passes attachments_by_message_id dict to template (Phase 5 Step 1)

## [2026-05-09] - Conversation attachments chat UI — attach & send (Phase 4)
- app/templates/agents/conversation.html: added paperclip button (left of send), hidden file input, and attachment chips area above input bar
- app/templates/agents/conversation.html: added CSS for .attach-chip, chip sub-elements, error state, #attach-btn hover, and @keyframes spin
- app/templates/agents/conversation.html: added JS — pendingAttachments/uploadsInProgress state, file picker wiring, handleFileSelected() with spinner→resolved chip flow, image thumbnail preview, truncate/showErrorChip/removeAttachment/updateChipsVisibility/updateSendButton helpers
- app/templates/agents/conversation.html: modified sendMessage() to include attachment_ids + attachment_metadata in request body and clear chips on success

## [2026-05-09] - Conversation attachments upload proxy and local storage (Phase 3)
- app/models.py: added MessageAttachment model (local metadata mirror; file lives on skunkBOX)
- migrations/928c0eaef896: migration for message_attachment table
- app/routes/agents.py: added _upload_attachment_to_skunkbox() helper with size/extension validation
- app/routes/agents.py: added POST /agents/<conv_id>/attachments upload proxy route
- app/routes/agents.py: added GET /agents/attachments/<id>/download ownership-checked proxy route
- app/routes/agents.py: send_message now accepts attachment_ids + attachment_metadata, forwards ids to skunkBOX, saves MessageAttachment rows after commit

## [2026-05-08] - UI polish + skunkBOX API logging

### Bug fixes
- **All Conversations filters** — replaced native `<select multiple>` list boxes with custom dropdown multi-selects for Agent and User; trigger shows "All agents" / "N selected"; checkboxes inside a styled panel; closes on outside click; sticky selection state preserved
- **Learning Center rate limit fix** — eliminated double API call on list page; now makes a single `limit=500` fetch and handles collection filtering + pagination entirely in Python, staying within the 10 RPM rate limit
- **AI Agents Config** — agent logo now renders as a clean round circle, matching the Conversations list; image wrapped in `overflow:hidden` div instead of relying on `border-radius` on the `<img>` tag alone

### External API request logging
- `_call_skunkbox_get()` and `_call_skunkbox()` in `agents.py` now write one `ApiRequestLog` row per call with `integration_id`, `integration_name`, `endpoint` (full URL), `method`, `status_code`, `latency_ms`, and `error_message`
- New `_log_api()` helper wraps the DB write in try/except so a logging failure never breaks the API call
- All skunkBOX traffic (chat messages, document list, document detail) now appears in Reporting → External API Requests

## [2026-05-08] - Learning Center collection tabs

### Feature
- Removed "Conversations" tab from the Learning Center tab bar
- Added **All Documents** as the first tab (shows all docs across all collections, includes Collection column)
- Added one tab per document collection, sorted A-Z — tabs are discovered dynamically by scanning the documents API response (no separate collections endpoint required)
- Collection column hidden when viewing a specific collection tab (redundant in that context)
- Pagination links now carry `?tab=<id>&page=N` so the active tab is preserved when paging
- `learning_center()` route makes one broad fetch (`limit=500`) to build the collections list, then a separate paginated fetch filtered by `collection_id` for the active tab

## [2026-05-08] - Navigation restructure + Conversations filter panel

### Home page change
- **Conversations (My Conversations) is now the default home page** — `/` and post-login redirect to `agents.list_conversations` instead of the old Dashboard
- All breadcrumb "Home" links and fallback redirects across every route file updated accordingly

### Dashboard moved to Reporting
- Dashboard removed from the left sidebar navigation
- Dashboard content (stat cards + Recent Release Notes) added as the **first tab** ("Dashboard") in the Reporting section (`/reporting/?tab=dashboard`)
- Reporting now defaults to the Dashboard tab
- `reporting.py` imports `Attribute`, `Role`, `ReleaseNote`; queries and passes `dash_stats` and `recent_releases` to the template
- Reporting tab bar switched to `tax-tab` / `tax-tabs` CSS pattern for consistency

### All Conversations filter panel
- Agent tiles hidden on the "All Conversations" tab
- Filter panel added (card with three controls): **Agent** multi-select, **User** multi-select (current user listed first as "My Conversations"), **Date Range** (from/to date pickers)
- **Apply** button submits filters via GET; **Clear** button appears only when filters are active
- Filter state is sticky (pre-selected after submit)
- `list_conversations()` in `agents.py` reads `agent_ids`, `user_ids`, `date_from`, `date_to` params and applies them to the query when `tab == "all"`; passes `all_users` and current filter state to template
- Date-to filter includes the full end day (23:59:59)
- Improved empty states: tab-aware messaging for Favorites, filtered All Conversations, and no-agent state

### Conversations — star / favorites
- Added `is_favorite` boolean column to `AgentConversation` (migration `75c0ec3212cc`)
- Star toggle button per conversation row; AJAX `POST /agents/<id>/favorite` flips the flag and returns JSON
- Three-tab navigation: **My Conversations** / **All Conversations** / **⭐ Favorites**
- Tab title shown as `<h1>` below the tab strip (matches User Management pattern)

### New Conversation modal
- "New Conversation" button in the top-right of the page header
- Modal with agent tile picker + large question textarea
- Agent auto-selected when only one exists; initial message passed as `?q=` param and auto-sent on conversation load

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
