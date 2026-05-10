import logging
import os
import subprocess
import threading
from pathlib import Path

import markdown
from flask import (Blueprint, abort, current_app, flash, jsonify,
                   redirect, render_template, request, url_for)
from flask_login import current_user, login_required

from ..access import permission_required
from ..activity_logger import log_activity
from ..extensions import db
from ..models import ReleaseNote, next_version
from ..release_manager import COLOR_HEX

help_bp = Blueprint("help", __name__, url_prefix="/help")
log = logging.getLogger(__name__)

# In-process generation status — resets on server restart
# Keyed by doc key; "all" covers all three docs
_gen_status: dict = {"running": False, "doc": None, "results": None, "error": None}

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"

DOC_FILES = {
    "quick_start": "QUICK_START.md",
    "user_manual": "USER_MANUAL.md",
    "architecture": "ARCHITECTURE.md",
    "dependencies": "PYTHON_DEPENDENCIES.md",
}

PAGE_META = {
    "release_notes": {
        "title": "Release Notes",
        "description": "A running changelog of product updates and improvements.",
    },
    "quick_start": {
        "title": "Quick Start Guide",
        "description": "Everything you need to get up and running fast.",
    },
    "user_manual": {
        "title": "User Manual",
        "description": "Comprehensive reference for all features and workflows.",
    },
    "architecture": {
        "title": "Architecture Overview",
        "description": "How the system is structured and why each layer exists.",
    },
    "dependencies": {
        "title": "Python Dependencies",
        "description": "All third-party packages used and their purpose.",
    },
}


def _render_doc(name: str) -> str:
    content = (DOCS_DIR / DOC_FILES[name]).read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    content = "".join(lines).lstrip("\n")
    return markdown.markdown(content, extensions=["tables", "fenced_code"])


def _user_guides_crumbs(tab: str) -> list:
    return [
        {"label": "Home", "url": url_for("agents.list_conversations")},
        {"label": "User Guides", "url": url_for("help.release_notes")},
        {"label": PAGE_META[tab]["title"], "url": None},
    ]


def _system_overview_crumbs(tab: str) -> list:
    return [
        {"label": "Home", "url": url_for("agents.list_conversations")},
        {"label": "System Overview", "url": url_for("help.architecture")},
        {"label": PAGE_META[tab]["title"], "url": None},
    ]


# ── Git helpers ───────────────────────────────────────────────────

def _repo_root() -> str:
    """Absolute path to the git repo root."""
    return os.path.normpath(
        os.path.join(current_app.root_path, "..")
    )


def _git(args: list, cwd: str) -> str | None:
    """Run a git command, return stdout or None on failure."""
    try:
        r = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, cwd=cwd,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except FileNotFoundError:
        return None  # git not installed


def _head_commit() -> str | None:
    return _git(["rev-parse", "HEAD"], _repo_root())


def _changelog_at(commit_hash: str) -> str | None:
    """Return CHANGELOG.md content at a specific commit, or None."""
    return _git(["show", f"{commit_hash}:CHANGELOG.md"], _repo_root())


def _new_changelog_lines(old_content: str, new_content: str) -> str:
    """Return changelog entries added since old_content.
    Finds the first ## heading in new_content that already exists in old_content;
    everything above that line is new."""
    old_headings = set()
    for ln in old_content.splitlines():
        if ln.startswith("## "):
            old_headings.add(ln.strip())

    new_lines = new_content.splitlines()
    cutoff = len(new_lines)
    for i, ln in enumerate(new_lines):
        if ln.startswith("## ") and ln.strip() in old_headings:
            cutoff = i
            break

    return "\n".join(new_lines[:cutoff]).strip()


# ── Routes ────────────────────────────────────────────────────────

@help_bp.route("/")
@login_required
@permission_required("help", "view")
def index():
    return redirect(url_for("help.release_notes"))


@help_bp.route("/release-notes")
@login_required
@permission_required("help", "view")
def release_notes():
    notes = (
        ReleaseNote.query
        .filter_by(status="published")
        .order_by(
            ReleaseNote.version_major.desc(),
            ReleaseNote.version_minor.desc(),
            ReleaseNote.version_patch.desc(),
        )
        .all()
    )
    meta = PAGE_META["release_notes"]
    return render_template(
        "help/release_notes.html",
        notes=notes,
        active_tab="release_notes",
        page_title=meta["title"],
        page_description=meta["description"],
        color_hex=COLOR_HEX,
        breadcrumbs=_user_guides_crumbs("release_notes"),
    )


@help_bp.route("/changelog-preview")
@login_required
@permission_required("help", "edit")
def changelog_preview():
    """Return new CHANGELOG.md lines since the last release commit hash (JSON)."""
    repo = _repo_root()

    # Current CHANGELOG.md content
    changelog_path = os.path.join(repo, "CHANGELOG.md")
    try:
        with open(changelog_path, "r", encoding="utf-8") as fh:
            current_content = fh.read()
    except FileNotFoundError:
        return jsonify({
            "entries": "", "entry_count": 0,
            "has_entries": False,
            "message": "CHANGELOG.md not found in repo root.",
        })

    # Most recent published release
    last = (
        ReleaseNote.query
        .filter_by(status="published")
        .order_by(ReleaseNote.published_at.desc())
        .first()
    )

    warning = ""
    last_published_utc = None

    if last and last.changelog_snapshot:
        # Best path: compare against the snapshot saved at generation time
        new_content = _new_changelog_lines(last.changelog_snapshot, current_content)
    elif last and last.changelog_commit_hash:
        # Legacy fallback: try to read CHANGELOG.md from git history
        old_content = _changelog_at(last.changelog_commit_hash)
        if old_content is None:
            new_content = current_content
            warning = f"⚠ Commit {last.changelog_commit_hash[:7]} not found — showing full changelog"
        else:
            new_content = _new_changelog_lines(old_content, current_content)
    else:
        new_content = current_content

    new_content = new_content.strip()
    has_entries = bool(new_content)

    if warning:
        message = warning
    elif last and (last.changelog_snapshot or last.changelog_commit_hash):
        last_published_utc = last.published_at.isoformat() if last.published_at else None
        if has_entries:
            message = f"Changes since v{last.version_string}"
        else:
            message = f"No new changelog entries since v{last.version_string}"
    else:
        message = ("Showing full changelog (no previous release)"
                   if has_entries else "No changelog entries found")

    entry_count = len([ln for ln in new_content.splitlines() if ln.startswith("## ")])
    return jsonify({
        "entries":            new_content,
        "entry_count":        entry_count,
        "has_entries":        has_entries,
        "message":            message,
        "last_published_utc": last_published_utc,
    })


@help_bp.route("/release-notes/generate", methods=["POST"])
@login_required
@permission_required("help", "edit")
def generate_release():
    if current_user.role != "admin":
        abort(403)

    raw_summary = (request.form.get("raw_summary") or "").strip()
    if not raw_summary:
        flash("Please paste a change summary.", "error")
        return redirect(url_for("help.release_notes"))

    release_type_override = (request.form.get("release_type_override") or "").strip().lower()
    if release_type_override not in ("patch", "minor", "major"):
        release_type_override = None

    try:
        from ..release_manager import create_release

        # Capture HEAD and CHANGELOG.md snapshot before creating,
        # so the next diff knows exactly where this release ended.
        head = _head_commit()
        repo = _repo_root()
        changelog_path = os.path.join(repo, "CHANGELOG.md")
        try:
            with open(changelog_path, "r", encoding="utf-8") as fh:
                changelog_snap = fh.read()
        except FileNotFoundError:
            changelog_snap = None

        note = create_release(raw_summary, current_user.id, release_type_override)

        if head:
            note.changelog_commit_hash = head
        if changelog_snap is not None:
            note.changelog_snapshot = changelog_snap
        if head or changelog_snap is not None:
            db.session.commit()

        flash(f"Release v{note.version_string} published successfully.", "success")
    except Exception as exc:
        log.error("Release generation error: %s", exc)
        flash(f"Generation failed: {exc}", "error")

    return redirect(url_for("help.release_notes"))


@help_bp.route("/release-notes/<int:note_id>/unpublish", methods=["POST"])
@login_required
@permission_required("help", "edit")
def unpublish_release(note_id):
    if current_user.role != "admin":
        abort(403)
    note = db.get_or_404(ReleaseNote, note_id)
    note.status = "draft"
    note.published_at = None
    db.session.commit()
    flash(f"v{note.version_string} moved back to draft.", "success")
    return redirect(url_for("help.release_notes"))


@help_bp.route("/regenerate", methods=["POST"])
@login_required
@permission_required("help", "edit")
def regenerate_doc():
    """Start async regeneration of one or all help documents."""
    if current_user.role != "admin":
        return jsonify({"ok": False, "error": "Admin only"}), 403

    doc = (request.form.get("doc") or request.get_json(silent=True) or {}).get("doc") \
        if request.is_json else request.form.get("doc", "all")
    # Normalise
    if isinstance(doc, dict):
        doc = doc.get("doc", "all")
    valid = {"quick_start", "user_manual", "architecture", "all"}
    if doc not in valid:
        doc = "all"

    if _gen_status["running"]:
        return jsonify({"ok": False, "error": "Generation already in progress"}), 409

    _gen_status["running"] = True
    _gen_status["doc"]     = doc
    _gen_status["results"] = None
    _gen_status["error"]   = None

    app     = current_app._get_current_object()
    user_id = current_user.id
    doc_keys = [doc] if doc != "all" else ["quick_start", "user_manual", "architecture"]

    def _run():
        with app.app_context():
            try:
                from ..doc_generator import regenerate_docs
                results = regenerate_docs(doc_keys, user_id)
                _gen_status["results"] = results
            except Exception as exc:
                log.error("Doc generation error: %s", exc)
                _gen_status["error"] = str(exc)
            finally:
                _gen_status["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "doc": doc})


@help_bp.route("/regen-status")
@login_required
@permission_required("help", "view")
def regen_status():
    """Poll endpoint — returns current generation status as JSON."""
    return jsonify({
        "running": _gen_status["running"],
        "doc":     _gen_status["doc"],
        "results": _gen_status["results"],
        "error":   _gen_status["error"],
        "done":    not _gen_status["running"] and (
            _gen_status["results"] is not None or _gen_status["error"] is not None
        ),
    })


@help_bp.route("/quick-start")
@login_required
@permission_required("help", "view")
def quick_start():
    meta = PAGE_META["quick_start"]
    return render_template(
        "help/doc_page.html",
        active_tab="quick_start",
        doc_name="quick_start",
        base_template="help/base_user_docs.html",
        content_html=_render_doc("quick_start"),
        page_title=meta["title"],
        page_description=meta["description"],
        gen_running=_gen_status["running"],
        breadcrumbs=_user_guides_crumbs("quick_start"),
    )


@help_bp.route("/user-manual")
@login_required
@permission_required("help", "view")
def user_manual():
    meta = PAGE_META["user_manual"]
    return render_template(
        "help/doc_page.html",
        active_tab="user_manual",
        doc_name="user_manual",
        base_template="help/base_user_docs.html",
        content_html=_render_doc("user_manual"),
        page_title=meta["title"],
        page_description=meta["description"],
        gen_running=_gen_status["running"],
        breadcrumbs=_user_guides_crumbs("user_manual"),
    )


@help_bp.route("/architecture")
@login_required
@permission_required("help", "view")
def architecture():
    meta = PAGE_META["architecture"]
    return render_template(
        "help/doc_page.html",
        active_tab="architecture",
        doc_name="architecture",
        base_template="help/base_system_overview.html",
        content_html=_render_doc("architecture"),
        page_title=meta["title"],
        page_description=meta["description"],
        gen_running=_gen_status["running"],
        breadcrumbs=_system_overview_crumbs("architecture"),
    )


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


@help_bp.route("/dependencies")
@login_required
@permission_required("help", "view")
def dependencies():
    meta = PAGE_META["dependencies"]
    return render_template(
        "help/doc_page.html",
        active_tab="dependencies",
        doc_name=None,
        base_template="help/base_system_overview.html",
        content_html=_render_doc("dependencies"),
        page_title=meta["title"],
        page_description=meta["description"],
        gen_running=False,
        breadcrumbs=_system_overview_crumbs("dependencies"),
    )
