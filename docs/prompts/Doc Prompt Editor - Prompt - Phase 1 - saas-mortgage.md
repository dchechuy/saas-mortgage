# Doc Prompt Editor — Phase 1 — saas-mortgage

## Context

`saas-mortgage` generates three help documents (Quick Start Guide, User Manual,
Architecture Overview) via `app/doc_generator.py`. The prompts that drive each
document — one shared system prompt and one user prompt per document type — are
currently hardcoded as Python string constants in that file.

This phase exposes those prompts through two distinct editing flows:

**Option 1 — Power user (System Config):**
Admin navigates to System Config → Help Prompts tab, reads the raw prompt,
clicks Edit, modifies it directly, saves, then clicks Regenerate.

**Option 2 — In-context (Help page):**
Admin is reading a help document (e.g. the User Manual), spots something to
change, clicks "Improve this doc", types a plain-English request
(e.g. "Split into numbered sections, start with Conversations"), and the AI
rewrites the prompt and shows a summary of what it changed. A confirmation
dialog then asks: "Want to regenerate now?"

---

## Files to Change

| File | What changes |
|---|---|
| `app/models.py` | Add `DocPrompt` model |
| `app/migrations/versions/<hash>_add_doc_prompt.py` | Generated migration |
| `app/__init__.py` | Import `DocPrompt`; seed in `_seed_defaults()` |
| `app/doc_generator.py` | Expose `DEFAULT_PROMPTS`; add `_get_doc_prompt()`; update generators |
| `app/routes/models.py` | Add save + reset routes (Option 1) |
| `app/routes/help.py` | Add `/improve/<doc_key>` and `/improve/<doc_key>/apply` routes (Option 2) |
| `app/templates/models/list.html` | Add "Help Prompts" tab (Option 1 UI) |
| `app/templates/help/doc_page.html` | Add "Improve this doc" button + modal (Option 2 UI) |

---

## Step 1 — Add `DocPrompt` model to `app/models.py`

Append after the `FeatureFlag` model (before `next_version`):

```python
class DocPrompt(db.Model):
    """Editable prompts used by the help-document generator."""
    __tablename__ = "doc_prompt"

    id          = db.Column(db.Integer, primary_key=True)
    key         = db.Column(db.String(40), unique=True, nullable=False)
    label       = db.Column(db.String(120), nullable=False)
    prompt_text = db.Column(db.Text, nullable=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)
```

---

## Step 2 — Generate and run migration

```bash
source .venv/bin/activate
flask db migrate -m "add doc_prompt table"
flask db upgrade
```

---

## Step 3 — Update `app/doc_generator.py`

### 3a — Replace `_SYSTEM_PROMPT` constant with `DEFAULT_PROMPTS` dict

Remove the existing `_SYSTEM_PROMPT` constant (lines 36–40).

Add this dict immediately after the `_DOCS_DIR` line:

```python
DEFAULT_PROMPTS = {
    "system": {
        "label": "System Prompt",
        "text": (
            "You are a technical writer creating user documentation for a SaaS platform. "
            "Write clear, friendly documentation that a non-technical user can follow. "
            "Use markdown formatting with headers, numbered steps, and bullet points."
        ),
    },
    "quick_start": {
        "label": "Quick Start Guide",
        "text": (
            "Based on these Flask route files, generate a Quick Start Guide for this SaaS platform.\n"
            "The platform is an internal tool that lets team members chat with AI agents, "
            "browse a Learning Center of documents, and manage configurations.\n\n"
            "The guide should:\n"
            "1. Start with a one-paragraph overview of what the platform is and who it's for\n"
            "2. List prerequisites (having login credentials)\n"
            "3. Provide 5-7 numbered steps to get started fast:\n"
            "   - Log in with your credentials\n"
            "   - Navigate the dashboard\n"
            "   - Start a conversation with an AI Agent\n"
            "   - Browse the Learning Center\n"
            "   - View your activity in Reporting\n"
            "4. End with a 'What\\'s next?' section pointing to the User Manual\n\n"
            "Format as clean markdown with a top-level # heading. Keep it under 600 words."
        ),
    },
    "user_manual": {
        "label": "User Manual",
        "text": (
            "Based on these Flask route files, generate a comprehensive User Manual "
            "for this SaaS platform.\n\n"
            "Structure it with a top-level # heading followed by sections:\n\n"
            "## Overview\n"
            "Brief description of the platform and its purpose.\n\n"
            "## Sections\n"
            "For each major section of the app, write:\n"
            "### [Section Name]\n"
            "**Purpose:** What this section does\n"
            "**Who can use it:** All users / Admin only\n"
            "**How to use it:** Step-by-step instructions\n"
            "**Key features:** Bullet list of capabilities\n\n"
            "Cover these sections in order:\n"
            "1. Dashboard\n"
            "2. AI Agents — Conversations (chat with AI agents, view message history)\n"
            "3. AI Agents — Learning Center (browse and preview documents)\n"
            "4. Reporting (activity logs, usage metrics)\n"
            "5. System Config — Users (manage team accounts)\n"
            "6. System Config — Roles & Permissions (access control)\n"
            "7. System Config — Models (AI model configuration)\n"
            "8. System Config — Integrations (external service connections)\n"
            "9. System Config — AI Agents (configure agent personas)\n"
            "10. System Config — Feature Flags (toggle platform features)\n"
            "11. User Guides / Help\n\n"
            "Format as clean markdown. Be thorough but concise."
        ),
    },
    "architecture": {
        "label": "Architecture Overview",
        "text": (
            "Based on these Flask route files, generate an Architecture Overview "
            "for this SaaS platform.\n\n"
            "Structure it with a top-level # heading followed by:\n\n"
            "## System Overview\n"
            "What the platform is built with and why.\n\n"
            "## Technology Stack\n"
            "A markdown table: Layer | Technology | Purpose\n"
            "Rows: Frontend, Backend, Database, Authentication, AI Integration, Web Server\n\n"
            "## Application Structure\n"
            "Describe the main components:\n"
            "- Flask blueprints and what each handles\n"
            "- SQLite database and key models\n"
            "- Integration with skunkBOX (external AI platform) via REST API\n"
            "- Role-based access control pattern\n\n"
            "## Request Flow\n"
            "Describe the flow: User → NGINX → Gunicorn → Flask blueprint → DB/API\n\n"
            "## Key Concepts\n"
            "Explain in plain English:\n"
            "- How AI Agents work (proxy to skunkBOX personas)\n"
            "- How Learning Center documents are served (proxy from skunkBOX)\n"
            "- How RAG sources are surfaced in conversations\n"
            "- How feature flags gate functionality\n\n"
            "Format as clean markdown."
        ),
    },
}
```

### 3b — Add `_get_doc_prompt()` helper

Add this function after `DEFAULT_PROMPTS`, before `_get_route_summaries`:

```python
def _get_doc_prompt(key: str) -> str:
    """Load prompt text from DB; fall back to DEFAULT_PROMPTS if not found."""
    try:
        from .models import DocPrompt
        row = DocPrompt.query.filter_by(key=key).first()
        if row:
            return row.prompt_text
    except Exception as exc:
        log.warning("Could not load DocPrompt '%s' from DB: %s", key, exc)
    return DEFAULT_PROMPTS[key]["text"]
```

### 3c — Update `_call_llm()` to load system prompt from DB

Replace the hardcoded `_SYSTEM_PROMPT` reference inside `_call_llm()`:

**Before:**
```python
{"role": "system", "content": _SYSTEM_PROMPT},
```

**After:**
```python
{"role": "system", "content": _get_doc_prompt("system")},
```

### 3d — Simplify the three generator functions

Replace each generator's inline prompt string with a `_get_doc_prompt()` call.
The route files context is appended at call time — it is NOT stored in the DB.

```python
def generate_quick_start(route_summaries, llm_model, user_id=None):
    routes_text = _format_routes(route_summaries)
    prompt = _get_doc_prompt("quick_start") + f"\n\nRoute files for context:\n{routes_text}"
    return _call_llm(prompt, llm_model, user_id=user_id)


def generate_user_manual(route_summaries, llm_model, user_id=None):
    routes_text = _format_routes(route_summaries)
    prompt = _get_doc_prompt("user_manual") + f"\n\nRoute files for context:\n{routes_text}"
    return _call_llm(prompt, llm_model, user_id=user_id)


def generate_architecture(route_summaries, llm_model, user_id=None):
    routes_text = _format_routes(route_summaries)
    prompt = _get_doc_prompt("architecture") + f"\n\nRoute files for context:\n{routes_text}"
    return _call_llm(prompt, llm_model, user_id=user_id)
```

---

## Step 4 — Seed defaults in `app/__init__.py`

### 4a — Add `DocPrompt` to the models import inside `_seed_defaults()`

```python
from .models import Attribute, DocPrompt, FeatureFlag, Integration, NavItem, NavSection, Permission, Role, User
```

### 4b — Add table guard

Add this alongside the other `inspector.has_table()` checks near the top of
`_seed_defaults()` (after the `nav_section` check):

```python
if not inspector.has_table("doc_prompt"):
    return
```

### 4c — Seed the four default prompts

Add before `db.session.commit()` at the end of `_seed_defaults()`:

```python
from .doc_generator import DEFAULT_PROMPTS
for key, meta in DEFAULT_PROMPTS.items():
    if not DocPrompt.query.filter_by(key=key).first():
        db.session.add(DocPrompt(key=key, label=meta["label"], prompt_text=meta["text"]))
```

---

## Step 5 — Option 1 routes in `app/routes/models.py`

Update the import to include `DocPrompt`:

```python
from ..models import AiAgent, Attribute, DocPrompt, FeatureFlag, Integration, LlmModel, NavItem, NavSection
```

Add these routes at the end of `models_bp`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Help Prompts — Option 1 (System Config direct edit)
# ─────────────────────────────────────────────────────────────────────────────

@models_bp.route("/doc-prompts/<key>/save", methods=["POST"])
@login_required
@permission_required("models", "edit")
def save_doc_prompt(key):
    from ..doc_generator import DEFAULT_PROMPTS
    if key not in DEFAULT_PROMPTS:
        flash(f"Unknown prompt key: {key}", "error")
        return _redirect_to_system_config("help-prompts")

    prompt_text = request.form.get("prompt_text", "").strip()
    if not prompt_text:
        flash("Prompt text cannot be empty.", "error")
        return _redirect_to_system_config("help-prompts")

    row = DocPrompt.query.filter_by(key=key).first()
    if row:
        row.prompt_text = prompt_text
    else:
        db.session.add(DocPrompt(
            key=key, label=DEFAULT_PROMPTS[key]["label"], prompt_text=prompt_text
        ))
    db.session.commit()
    log_activity(current_user, "doc_prompt.saved", page="System Config")
    flash(f"'{DEFAULT_PROMPTS[key]['label']}' prompt saved.", "success")
    return _redirect_to_system_config("help-prompts")


@models_bp.route("/doc-prompts/<key>/reset", methods=["POST"])
@login_required
@permission_required("models", "edit")
def reset_doc_prompt(key):
    from ..doc_generator import DEFAULT_PROMPTS
    if key not in DEFAULT_PROMPTS:
        flash(f"Unknown prompt key: {key}", "error")
        return _redirect_to_system_config("help-prompts")

    row = DocPrompt.query.filter_by(key=key).first()
    if row:
        row.prompt_text = DEFAULT_PROMPTS[key]["text"]
    else:
        db.session.add(DocPrompt(
            key=key, label=DEFAULT_PROMPTS[key]["label"],
            prompt_text=DEFAULT_PROMPTS[key]["text"]
        ))
    db.session.commit()
    log_activity(current_user, "doc_prompt.reset", page="System Config")
    flash(f"'{DEFAULT_PROMPTS[key]['label']}' reset to default.", "success")
    return _redirect_to_system_config("help-prompts")
```

---

## Step 6 — Option 2 routes in `app/routes/help.py`

Add two new routes to `help_bp`. These handle the "Improve this doc" flow.

### 6a — `POST /help/improve/<doc_key>` — AI rewrites the prompt

This route is called via AJAX from the modal. It:
1. Takes the user's plain-English `instruction`
2. Loads the current prompt from DB (or default)
3. Calls the LLM with a meta-prompt asking it to rewrite the prompt
4. Returns JSON: `{ok, updated_prompt, summary}`

```python
@help_bp.route("/improve/<doc_key>", methods=["POST"])
@login_required
@permission_required("help", "edit")
def improve_doc_prompt(doc_key):
    """AJAX: AI rewrites a doc-generation prompt based on a plain-English instruction."""
    from ..models import DocPrompt, LlmModel
    from ..doc_generator import DEFAULT_PROMPTS, _call_llm
    import json as _json

    valid_keys = {"quick_start", "user_manual", "architecture"}
    if doc_key not in valid_keys:
        return jsonify({"ok": False, "error": "Invalid document key"}), 400

    data = request.get_json(silent=True) or {}
    instruction = (data.get("instruction") or "").strip()
    if not instruction:
        return jsonify({"ok": False, "error": "Instruction cannot be empty"}), 400

    # Load current prompt
    row = DocPrompt.query.filter_by(key=doc_key).first()
    current_prompt = row.prompt_text if row else DEFAULT_PROMPTS[doc_key]["text"]

    # Pick the active LLM model
    llm_model = (
        LlmModel.query.filter_by(is_default=True, is_active=True).first()
        or LlmModel.query.filter_by(is_active=True).first()
    )
    if not llm_model:
        return jsonify({"ok": False, "error": "No active AI model configured"}), 500

    meta_prompt = (
        "You are a prompt engineer. Below is the current prompt used to generate a help document.\n"
        "A user has requested the following improvement:\n\n"
        f'"{instruction}"\n\n'
        "Current prompt:\n"
        "---\n"
        f"{current_prompt}\n"
        "---\n\n"
        "Return a JSON object with exactly two keys:\n"
        '  "updated_prompt": the full rewritten prompt text incorporating the request\n'
        '  "summary": one short paragraph (2-3 sentences) describing what you changed and why,\n'
        "             written directly to the user in plain English\n\n"
        "Return only valid JSON. No markdown fences, no extra text."
    )

    try:
        raw = _call_llm(meta_prompt, llm_model, user_id=current_user.id)
        # Strip markdown fences if the model added them anyway
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = _json.loads(raw)
        updated_prompt = result.get("updated_prompt", "").strip()
        summary = result.get("summary", "").strip()
        if not updated_prompt:
            raise ValueError("LLM returned empty updated_prompt")
    except Exception as exc:
        log.error("improve_doc_prompt failed for '%s': %s", doc_key, exc)
        return jsonify({"ok": False, "error": f"AI call failed: {exc}"}), 500

    return jsonify({
        "ok": True,
        "doc_key": doc_key,
        "updated_prompt": updated_prompt,
        "summary": summary,
    })
```

### 6b — `POST /help/improve/<doc_key>/apply` — save and optionally regenerate

```python
@help_bp.route("/improve/<doc_key>/apply", methods=["POST"])
@login_required
@permission_required("help", "edit")
def apply_improved_prompt(doc_key):
    """Save the AI-rewritten prompt and optionally kick off regeneration."""
    from ..models import DocPrompt
    from ..doc_generator import DEFAULT_PROMPTS

    valid_keys = {"quick_start", "user_manual", "architecture"}
    if doc_key not in valid_keys:
        return jsonify({"ok": False, "error": "Invalid document key"}), 400

    data = request.get_json(silent=True) or {}
    updated_prompt = (data.get("updated_prompt") or "").strip()
    regenerate = bool(data.get("regenerate", False))

    if not updated_prompt:
        return jsonify({"ok": False, "error": "Updated prompt cannot be empty"}), 400

    label = DEFAULT_PROMPTS.get(doc_key, {}).get("label", doc_key)
    row = DocPrompt.query.filter_by(key=doc_key).first()
    if row:
        row.prompt_text = updated_prompt
    else:
        db.session.add(DocPrompt(key=doc_key, label=label, prompt_text=updated_prompt))
    db.session.commit()
    log_activity(current_user, "doc_prompt.improved", page="Help")

    if regenerate:
        # Reuse the existing async regeneration logic
        if _gen_status["running"]:
            return jsonify({"ok": True, "saved": True, "regenerating": False,
                            "warning": "Regeneration already in progress"}), 200

        _gen_status.update({"running": True, "doc": doc_key, "results": None, "error": None})
        app_obj = current_app._get_current_object()
        user_id = current_user.id

        def _run():
            with app_obj.app_context():
                try:
                    from ..doc_generator import regenerate_docs
                    results = regenerate_docs([doc_key], user_id)
                    _gen_status["results"] = results
                except Exception as exc:
                    log.error("Regen after improve failed: %s", exc)
                    _gen_status["error"] = str(exc)
                finally:
                    _gen_status["running"] = False

        import threading
        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"ok": True, "saved": True, "regenerating": True})

    return jsonify({"ok": True, "saved": True, "regenerating": False})
```

---

## Step 7 — Option 1 UI: "Help Prompts" tab in System Config

### 7a — Pass data to the template

In `list_models()` in `app/routes/models.py`, add to the `render_template()` call:

```python
from ..models import DocPrompt
from ..doc_generator import DEFAULT_PROMPTS
...
doc_prompts=DocPrompt.query.order_by(DocPrompt.id).all(),
default_prompts=DEFAULT_PROMPTS,
```

### 7b — Tab button

Add alongside the other tab buttons in `templates/models/list.html`:

```html
<button class="tab-btn" data-tab="help-prompts">Help Prompts</button>
```

### 7c — Tab panel

```html
<div class="tab-panel" id="tab-help-prompts">
  <div class="panel-header">
    <h2>Help Prompts</h2>
    <p class="panel-description">
      These prompts control what the AI writes when you regenerate Quick Start,
      User Manual, and Architecture documents. Edit any prompt, save, then
      regenerate the document from the User Guides section.
      The System Prompt applies to all three.
    </p>
  </div>

  {% set prompt_map = {} %}
  {% for p in doc_prompts %}{% if prompt_map.update({p.key: p}) %}{% endif %}{% endfor %}

  {% for key, meta in default_prompts.items() %}
    {% set current = prompt_map.get(key) %}
    {% set current_text = current.prompt_text if current else meta.text %}
    <div class="card mb-4">
      <div class="card-header" style="display: flex; align-items: center; justify-content: space-between;">
        <h3 style="margin: 0;">{{ meta.label }}</h3>
        {% if current %}
          <span class="badge badge-muted" style="font-size: 0.75rem;">
            Updated <span class="local-time" data-utc="{{ current.updated_at.isoformat() }}">
              {{ current.updated_at.strftime('%Y-%m-%d') }}
            </span>
          </span>
        {% endif %}
      </div>
      <div class="card-body">
        <form method="POST" action="{{ url_for('models.save_doc_prompt', key=key) }}">
          <textarea name="prompt_text" rows="10"
                    class="form-control"
                    style="font-family: monospace; font-size: 0.82rem; width: 100%;">{{ current_text }}</textarea>
          <div style="display: flex; gap: 0.5rem; margin-top: 0.75rem; align-items: center;">
            <button type="submit" class="btn btn-primary">Save</button>
            <form method="POST"
                  action="{{ url_for('models.reset_doc_prompt', key=key) }}"
                  style="margin: 0;"
                  onsubmit="return confirm('Reset to default? This will overwrite your current text.');">
              <button type="submit" class="btn btn-secondary btn-sm">Reset to Default</button>
            </form>
          </div>
        </form>
      </div>
    </div>
  {% endfor %}
</div>
```

---

## Step 8 — Option 2 UI: "Improve this doc" on Help doc pages

Edit `app/templates/help/doc_page.html`.

### 8a — Add the button

Find the area where the "Regenerate" button is shown (visible to admins only).
Add the "Improve this doc" button next to it. Only show it for the three
AI-generated docs (not the dependencies page where `doc_name` is None):

```html
{% if current_user.role == 'admin' and doc_name in ('quick_start', 'user_manual', 'architecture') %}
  <button class="btn btn-secondary"
          id="improve-btn"
          data-doc-key="{{ doc_name }}"
          onclick="openImproveModal()">
    Improve this doc
  </button>
{% endif %}
```

### 8b — Add the modal

Place before `{% endblock %}`:

```html
{% if current_user.role == 'admin' and doc_name in ('quick_start', 'user_manual', 'architecture') %}
<div id="improve-modal" class="modal-backdrop" style="display: none;">
  <div class="modal" style="max-width: 560px; width: 100%;">

    <!-- Step 1: Enter instruction -->
    <div id="improve-step-1">
      <div class="modal-header">
        <h3>Improve This Document</h3>
        <button class="btn-icon" onclick="closeImproveModal()">✕</button>
      </div>
      <div class="modal-body">
        <p style="margin-bottom: 0.75rem; color: var(--text-muted); font-size: 0.9rem;">
          Describe what you'd like to change. The AI will rewrite the generation
          prompt and show you exactly what it did before you commit.
        </p>
        <textarea id="improve-instruction"
                  rows="4"
                  class="form-control"
                  placeholder='e.g. "Split into numbered sections. Start with Conversations."'
                  style="width: 100%;"></textarea>
        <p id="improve-error" style="color: var(--danger); font-size: 0.85rem; margin-top: 0.5rem; display: none;"></p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="closeImproveModal()">Cancel</button>
        <button class="btn btn-primary" id="improve-submit-btn" onclick="submitImprovement()">
          Ask AI to Improve
        </button>
      </div>
    </div>

    <!-- Step 2: Confirmation -->
    <div id="improve-step-2" style="display: none;">
      <div class="modal-header">
        <h3>Review Changes</h3>
      </div>
      <div class="modal-body">
        <p style="font-weight: 600; margin-bottom: 0.5rem;">What the AI changed:</p>
        <p id="improve-summary"
           style="background: var(--panel-alt); border-radius: 6px;
                  padding: 0.75rem; font-size: 0.9rem; line-height: 1.5;
                  color: var(--text); margin-bottom: 1rem;"></p>
        <details>
          <summary style="cursor: pointer; font-size: 0.85rem; color: var(--text-muted);">
            View updated prompt
          </summary>
          <pre id="improve-updated-prompt"
               style="font-size: 0.78rem; background: var(--panel-alt);
                      border-radius: 6px; padding: 0.75rem; margin-top: 0.5rem;
                      white-space: pre-wrap; word-break: break-word;
                      max-height: 200px; overflow-y: auto;"></pre>
        </details>
      </div>
      <div class="modal-footer" style="gap: 0.5rem;">
        <button class="btn btn-secondary" onclick="closeImproveModal()">Cancel</button>
        <button class="btn btn-secondary" onclick="applyImprovement(false)">
          Save Prompt Only
        </button>
        <button class="btn btn-primary" onclick="applyImprovement(true)">
          Save &amp; Regenerate
        </button>
      </div>
    </div>

    <!-- Step 3: Applying -->
    <div id="improve-step-3" style="display: none;">
      <div class="modal-body" style="text-align: center; padding: 2rem;">
        <p id="improve-applying-msg" style="color: var(--text-muted);">Saving prompt…</p>
      </div>
    </div>

  </div>
</div>

<script>
  const DOC_KEY = "{{ doc_name }}";
  let _updatedPrompt = "";

  function openImproveModal() {
    document.getElementById("improve-modal").style.display = "flex";
    document.getElementById("improve-step-1").style.display = "block";
    document.getElementById("improve-step-2").style.display = "none";
    document.getElementById("improve-step-3").style.display = "none";
    document.getElementById("improve-instruction").value = "";
    document.getElementById("improve-error").style.display = "none";
    document.getElementById("improve-instruction").focus();
  }

  function closeImproveModal() {
    document.getElementById("improve-modal").style.display = "none";
  }

  async function submitImprovement() {
    const instruction = document.getElementById("improve-instruction").value.trim();
    const errEl = document.getElementById("improve-error");
    if (!instruction) {
      errEl.textContent = "Please describe what you'd like to change.";
      errEl.style.display = "block";
      return;
    }
    errEl.style.display = "none";
    const btn = document.getElementById("improve-submit-btn");
    btn.disabled = true;
    btn.textContent = "Thinking…";

    try {
      const resp = await fetch(`/help/improve/${DOC_KEY}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({instruction}),
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "Unknown error");

      _updatedPrompt = data.updated_prompt;
      document.getElementById("improve-summary").textContent = data.summary;
      document.getElementById("improve-updated-prompt").textContent = data.updated_prompt;

      document.getElementById("improve-step-1").style.display = "none";
      document.getElementById("improve-step-2").style.display = "block";
    } catch (err) {
      errEl.textContent = "Error: " + err.message;
      errEl.style.display = "block";
    } finally {
      btn.disabled = false;
      btn.textContent = "Ask AI to Improve";
    }
  }

  async function applyImprovement(regenerate) {
    document.getElementById("improve-step-2").style.display = "none";
    document.getElementById("improve-step-3").style.display = "block";
    document.getElementById("improve-applying-msg").textContent =
      regenerate ? "Saving prompt and starting regeneration…" : "Saving prompt…";

    try {
      const resp = await fetch(`/help/improve/${DOC_KEY}/apply`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({updated_prompt: _updatedPrompt, regenerate}),
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error || "Unknown error");

      closeImproveModal();
      if (regenerate && data.regenerating) {
        // Reload after a short delay so the regen-status polling can start
        setTimeout(() => window.location.reload(), 800);
      }
    } catch (err) {
      document.getElementById("improve-applying-msg").textContent = "Error: " + err.message;
    }
  }
</script>
{% endif %}
```

---

## Step 9 — Verify end-to-end

### Option 1 flow

1. `flask db upgrade && python run.py`
2. Log in as admin → System Config → Help Prompts tab
3. All four prompts appear with their default text
4. Edit the User Manual prompt → Save → flash "User Manual prompt saved"
5. Navigate to Help → User Manual → Regenerate → confirm updated output

### Option 2 flow

1. Log in as admin → Help → User Manual
2. Click "Improve this doc"
3. Type: `"Split into numbered sections. Start with Conversations."`
4. Click "Ask AI to Improve"
5. Modal shows the AI's summary of what it changed
6. Expand "View updated prompt" to see the rewrite
7. Click "Save & Regenerate"
8. Page reloads; regen-status polling shows progress
9. Navigate back to User Manual — confirm the document reflects the change
10. Go to System Config → Help Prompts → confirm the User Manual prompt matches what the AI wrote

### Reset flow

1. System Config → Help Prompts → User Manual → Reset to Default
2. Confirm dialog → prompt reverts to original text

---

## Commit

```bash
git add app/models.py app/doc_generator.py app/routes/models.py \
        app/routes/help.py app/__init__.py \
        app/templates/models/list.html app/templates/help/doc_page.html \
        migrations/
git commit -m "Add editable help prompts with direct edit (Option 1) and AI-assisted improve flow (Option 2)"
```

---

## Do Not Change

- `app/doc_generator.py` — `regenerate_docs()`, `_save_doc()`, `_get_route_summaries()`,
  `_format_routes()`, `_call_llm()` internals (only the `_SYSTEM_PROMPT` reference changes)
- `app/page_registry.py` — "Help Prompts" lives under the existing `models` page slug
- `app/routes/help.py` — the existing `/regenerate` and `/regen-status` routes are unchanged;
  Option 2 adds two new routes alongside them
- Any migration files other than the new one

---

## Expected Outcome

Two complementary editing flows with no duplication:

- **Power users** can read and directly edit raw prompts in System Config
- **In-context users** can describe what they want in plain English and let the AI
  handle the prompt rewrite, with a confirmation step before anything is committed
- Both flows write to the same `DocPrompt` DB rows, so changes from either are
  visible in both places
- Regeneration is always opt-in — saving a prompt never automatically changes
  the published document
