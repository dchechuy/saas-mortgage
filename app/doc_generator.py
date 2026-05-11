"""Help documentation generator for saas-mortgage.

Reads route source files, calls Azure OpenAI via LlmModel, and saves
the generated markdown back to docs/*.md files.

Adapted from skunkBOX — no Document Center or ChromaDB; docs are flat
markdown files served directly by the help blueprint.
"""
import logging
import os
import time
from pathlib import Path

import requests as http_requests

from .crypto import decrypt_value
from .extensions import db
from .models import LlmModel, LlmRequestLog

log = logging.getLogger(__name__)

# Route files that provide context for doc generation (relative to project root)
_ROUTE_FILES = [
    "app/routes/auth.py",
    "app/routes/users.py",
    "app/routes/main.py",
    "app/routes/agents.py",
    "app/routes/models.py",
    "app/routes/permissions.py",
    "app/routes/reporting.py",
]

# docs/ directory (two levels up from this file's package)
_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"

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


# ── Source reading ────────────────────────────────────────────────

def _get_route_summaries() -> dict:
    """Read route source files from the project root.

    Returns {filename: source_code}, skipping missing files.
    """
    base = str(_DOCS_DIR.parent)
    result = {}
    for rel_path in _ROUTE_FILES:
        full_path = os.path.join(base, rel_path)
        if not os.path.exists(full_path):
            log.warning("Route file not found, skipping: %s", full_path)
            continue
        try:
            with open(full_path, "r", encoding="utf-8") as fh:
                result[os.path.basename(rel_path)] = fh.read()
        except Exception as exc:
            log.warning("Could not read %s: %s", rel_path, exc)
    return result


def _format_routes(route_summaries: dict) -> str:
    parts = []
    for fname, src in route_summaries.items():
        snippet = src[:5000] + ("\n...(truncated)..." if len(src) > 5000 else "")
        parts.append(f"=== {fname} ===\n{snippet}")
    return "\n\n".join(parts)


# ── LLM call ─────────────────────────────────────────────────────

def _get_model() -> LlmModel:
    return (
        LlmModel.query.filter_by(is_default=True, is_active=True).first()
        or LlmModel.query.filter_by(is_active=True, model_type="chat").first()
        or LlmModel.query.filter_by(is_active=True).first()
    )


def _call_llm(prompt: str, llm_model: LlmModel, user_id: int = None) -> str:
    api_key = decrypt_value(llm_model.api_key_encrypted)
    url = llm_model.endpoint_url.rstrip("/") + "/chat/completions"
    started = time.time()

    def _log(status="success", prompt_tokens=None, completion_tokens=None,
             total_tokens=None, error_message=None):
        latency_ms = int((time.time() - started) * 1000)
        entry = LlmRequestLog(
            model_id=llm_model.id,
            model_name=llm_model.name,
            use_case="doc_generation",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
        )
        try:
            db.session.add(entry)
            db.session.commit()
        except Exception:
            db.session.rollback()

    try:
        resp = http_requests.post(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "model": llm_model.deployment_name,
                "messages": [
                    {"role": "system", "content": _get_doc_prompt("system")},
                    {"role": "user",   "content": prompt},
                ],
                "max_completion_tokens": 4000,
            },
            timeout=120,
        )
        if not resp.ok:
            _log(status="error",
                 error_message=f"Azure API error {resp.status_code}")
            raise RuntimeError(f"Azure API error {resp.status_code} — {resp.text[:400]}")

        data = resp.json()
        usage = data.get("usage", {})
        _log(
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        return data["choices"][0]["message"]["content"]

    except RuntimeError:
        raise
    except Exception as exc:
        msg = str(exc) or repr(exc) or type(exc).__name__
        _log(status="error", error_message=msg)
        raise RuntimeError(f"{type(exc).__name__}: {msg}") from exc


# ── Document generators ───────────────────────────────────────────

def generate_quick_start(route_summaries: dict, llm_model: LlmModel,
                          user_id: int = None) -> str:
    routes_text = _format_routes(route_summaries)
    prompt = _get_doc_prompt("quick_start") + f"\n\nRoute files for context:\n{routes_text}"
    return _call_llm(prompt, llm_model, user_id=user_id)


def generate_user_manual(route_summaries: dict, llm_model: LlmModel,
                          user_id: int = None) -> str:
    routes_text = _format_routes(route_summaries)
    prompt = _get_doc_prompt("user_manual") + f"\n\nRoute files for context:\n{routes_text}"
    return _call_llm(prompt, llm_model, user_id=user_id)


def generate_architecture(route_summaries: dict, llm_model: LlmModel,
                           user_id: int = None) -> str:
    routes_text = _format_routes(route_summaries)
    prompt = _get_doc_prompt("architecture") + f"\n\nRoute files for context:\n{routes_text}"
    return _call_llm(prompt, llm_model, user_id=user_id)


# ── Save to docs/ ─────────────────────────────────────────────────

_DOC_FILES = {
    "quick_start":  "QUICK_START.md",
    "user_manual":  "USER_MANUAL.md",
    "architecture": "ARCHITECTURE.md",
}

_DOC_LABELS = {
    "quick_start":  "Quick Start Guide",
    "user_manual":  "User Manual",
    "architecture": "Architecture Overview",
}


def _save_doc(key: str, content: str) -> None:
    """Write generated content to the appropriate docs/*.md file."""
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _DOCS_DIR / _DOC_FILES[key]
    dest.write_text(content, encoding="utf-8")
    log.info("Saved generated doc: %s", dest)


# ── Orchestrator ──────────────────────────────────────────────────

_GENERATORS = {
    "quick_start":  generate_quick_start,
    "user_manual":  generate_user_manual,
    "architecture": generate_architecture,
}


def regenerate_docs(doc_keys: list[str], user_id: int) -> dict:
    """Generate and save one or more help documents.

    ``doc_keys`` is a list of keys from {"quick_start", "user_manual", "architecture"}.
    Pass ``["all"]`` or the full list to regenerate everything.

    Returns::

        {
            "quick_start":  {"ok": True,  "label": "Quick Start Guide"},
            "user_manual":  {"ok": False, "error": "..."},
            ...
        }
    """
    if doc_keys == ["all"] or set(doc_keys) >= set(_GENERATORS):
        doc_keys = list(_GENERATORS)

    model = _get_model()
    if not model:
        err = "No active AI model configured. Add one in System Config → Models."
        return {k: {"ok": False, "error": err} for k in doc_keys}

    route_summaries = _get_route_summaries()
    results = {}

    for key in doc_keys:
        if key not in _GENERATORS:
            results[key] = {"ok": False, "error": f"Unknown doc key: {key}"}
            continue
        try:
            gen_fn = _GENERATORS[key]
            content = gen_fn(route_summaries, model, user_id=user_id)
            _save_doc(key, content)
            results[key] = {"ok": True, "label": _DOC_LABELS[key]}
            log.info("Generated and saved: %s", _DOC_LABELS[key])
        except Exception as exc:
            import traceback as _tb
            msg = str(exc) or repr(exc) or type(exc).__name__
            log.error("Failed to generate '%s': %s\n%s",
                      _DOC_LABELS.get(key, key), msg, _tb.format_exc())
            results[key] = {"ok": False, "error": msg}

    return results
