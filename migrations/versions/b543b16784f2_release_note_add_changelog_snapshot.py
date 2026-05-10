"""release_note_add_changelog_snapshot

Revision ID: b543b16784f2
Revises: 928c0eaef896
Create Date: 2026-05-10 12:32:47.053453

Adds changelog_snapshot (TEXT) to release_note so that the Generate Release
Notes preview always diffs against the exact CHANGELOG.md text that was live
when the previous release was published — no git history required.

Also backfills v1.0.0 with the CHANGELOG.md content that was current at the
time it was generated (commit 716041c), so the next release correctly shows
only entries added after that point.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b543b16784f2'
down_revision = '928c0eaef896'
branch_labels = None
depends_on = None

# CHANGELOG.md content at commit 716041c (last May-8 commit — the baseline for v1.0.0)
_V1_SNAPSHOT = """\
# Changelog

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
- Fixed broken Edit button in System Config > Attributes

## [2026-05-07] - AI Agents feature + UI polish

### AI Agents feature
- Added `AiAgent`, `AgentConversation`, `AgentMessage` models to `app/models.py`

## [2026-05-06] - Documentation + sidebar + LLM Models UI

### Documentation restructure
- Split help section into two pages: User Guides and System Overview

## [2026-05-06] - Initial cleanup — align with skunkBOX principles

- Removed unauthenticated `/bootstrap/reset-admin` endpoint (security hole)
- Fixed deprecated SQLAlchemy patterns
"""


def upgrade():
    with op.batch_alter_table('release_note', schema=None) as batch_op:
        batch_op.add_column(sa.Column('changelog_snapshot', sa.Text(), nullable=True))

    # Backfill v1.0.0: set its snapshot to the CHANGELOG.md baseline at release time.
    # The stored commit hash (451b8c1a) predates CHANGELOG.md, so git can't provide
    # the old content — we embed the content directly here.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE release_note SET changelog_snapshot = :snap "
            "WHERE version_string = '1.0.0' AND changelog_snapshot IS NULL"
        ),
        {"snap": _V1_SNAPSHOT},
    )


def downgrade():
    with op.batch_alter_table('release_note', schema=None) as batch_op:
        batch_op.drop_column('changelog_snapshot')
