"""Release notes manager — versioning, codename cycling, AI generation.

Adapted from skunkBOX for saas-mortgage:
  - Uses LlmModel instead of AzureModel
  - Logs to LlmRequestLog directly (no llm_logger helper)
  - Derives codename cycling index from existing release count
"""
import logging
import time
from datetime import datetime

import requests as http_requests

from .activity_logger import log_activity, reraise_if_testing
from .crypto import decrypt_value
from .extensions import db
from .models import LlmModel, LlmRequestLog, ReleaseNote, User

log = logging.getLogger(__name__)

# ── Codename seed lists ───────────────────────────────────────────

COLORS = [
    "Amber", "Blue", "Coral", "Crimson", "Emerald",
    "Fuchsia", "Gold", "Indigo", "Jade", "Lavender",
    "Magenta", "Navy", "Olive", "Onyx", "Pearl",
    "Plum", "Ruby", "Sage", "Scarlet", "Silver",
    "Teal", "Topaz", "Violet", "White", "Yellow",
]

MAMMALS = [
    "Armadillo", "Badger", "Bear", "Bison", "Bobcat",
    "Capybara", "Cheetah", "Chinchilla", "Chipmunk",
    "Coyote", "Dingo", "Dolphin", "Elephant", "Elk",
    "Ferret", "Fox", "Gazelle", "Gibbon", "Gopher",
    "Gorilla", "Hedgehog", "Hyena", "Jaguar", "Kangaroo",
    "Koala", "Lemur", "Leopard", "Lion", "Llama",
    "Lynx", "Manatee", "Meerkat", "Mink", "Mongoose",
    "Moose", "Narwhal", "Ocelot", "Otter", "Panda",
    "Panther", "Platypus", "Porcupine", "Quokka",
    "Rabbit", "Raccoon", "Reindeer", "Rhinoceros",
    "Salamander", "Sloth", "Squirrel", "Tiger",
    "Walrus", "Weasel", "Wolf", "Wolverine", "Yak", "Zebra",
]

# Color name → hex for banner gradients
COLOR_HEX = {
    "Amber":    "#F59E0B", "Blue":    "#3B82F6", "Coral":   "#F97316",
    "Crimson":  "#DC2626", "Emerald": "#10B981", "Fuchsia": "#D946EF",
    "Gold":     "#EAB308", "Indigo":  "#6366F1", "Jade":    "#059669",
    "Lavender": "#7C3AED", "Magenta": "#EC4899", "Navy":    "#1E40AF",
    "Olive":    "#84CC16", "Onyx":    "#374151", "Pearl":   "#9CA3AF",
    "Plum":     "#7C3AED", "Ruby":    "#E11D48", "Sage":    "#6B7280",
    "Scarlet":  "#DC2626", "Silver":  "#6B7280", "Teal":    "#14B8A6",
    "Topaz":    "#0EA5E9", "Violet":  "#8B5CF6", "White":   "#F9FAFB",
    "Yellow":   "#EAB308",
}


def _codename_color_hex(codename: str) -> str:
    """Extract hex color from codename string like 'Emerald Wolverine'."""
    if not codename:
        return "#4361ee"
    color = codename.split()[0]
    return COLOR_HEX.get(color, "#4361ee")


# ── Internal LLM call ─────────────────────────────────────────────

def _call_llm(system: str, user_msg: str, llm_model: LlmModel,
              max_tokens: int = 2000, user_id: int = None) -> str:
    """POST to Azure OpenAI chat completions. Logs result to LlmRequestLog."""
    api_key = decrypt_value(llm_model.api_key_encrypted)
    url = llm_model.endpoint_url.rstrip("/") + "/chat/completions"
    started = time.time()

    def _log(status="success", prompt_tokens=None, completion_tokens=None,
             total_tokens=None, error_message=None):
        from .tenant_context import get_active_tenant_id

        latency_ms = int((time.time() - started) * 1000)
        acting_user = db.session.get(User, user_id) if user_id else None
        tenant_id = get_active_tenant_id(acting_user)
        if tenant_id is None:
            return
        entry = LlmRequestLog(
            tenant_id=tenant_id,
            model_id=llm_model.id,
            model_name=llm_model.name,
            use_case="release_notes",
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
            reraise_if_testing()

    try:
        resp = http_requests.post(
            url,
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "model": llm_model.deployment_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                "max_completion_tokens": max_tokens,
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
        _log(status="error", error_message=str(exc))
        raise


# ── Codename cycling ──────────────────────────────────────────────

def get_next_codename() -> str:
    """Return the next codename based on the current count of published releases."""
    # Use total release count as cycling index (no separate table needed)
    index = ReleaseNote.query.count()
    color  = COLORS[index % len(COLORS)]
    mammal = MAMMALS[index % len(MAMMALS)]
    return f"{color} {mammal}"


# ── Version management ────────────────────────────────────────────

def get_last_version() -> tuple:
    """Return (major, minor, patch) of the most recent published release, or (0,0,0)."""
    last = (
        ReleaseNote.query
        .filter_by(status="published")
        .order_by(
            ReleaseNote.version_major.desc(),
            ReleaseNote.version_minor.desc(),
            ReleaseNote.version_patch.desc(),
        )
        .first()
    )
    if last is None:
        return (0, 0, 0)
    return (last.version_major, last.version_minor, last.version_patch)


def calculate_next_version(release_type: str) -> tuple:
    major, minor, patch = get_last_version()
    if release_type == "major":
        return (major + 1, 0, 0)
    if release_type == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


# ── AI classification & generation ───────────────────────────────

def determine_release_type(summary_text: str, llm_model: LlmModel,
                            user_id: int = None) -> str:
    """Classify the release type using AI. Falls back to 'minor' on any error."""
    # Quick heuristic: 8+ bullet points → major
    bullet_count = len([ln for ln in summary_text.split("\n")
                        if ln.strip().startswith("-")])
    if bullet_count >= 8:
        return "major"

    system = (
        "You are a software release classifier. "
        "Respond with ONLY one word: major, minor, or patch"
    )
    user_prompt = (
        "Based on this change summary, classify the release type:\n\n"
        "MAJOR: New major sections or modules, multiple new features, "
        "architectural changes, 5+ significant changes\n"
        "MINOR: 1-4 new features, significant UI improvements, new settings\n"
        "PATCH: Bug fixes only, small tweaks, label changes\n\n"
        f"Summary:\n{summary_text}\n\n"
        "Respond with exactly one word: major, minor, or patch"
    )
    try:
        result = _call_llm(system, user_prompt, llm_model,
                           max_tokens=10, user_id=user_id).strip().lower()
        if result in ("major", "minor", "patch"):
            return result
        for word in ("major", "minor", "patch"):
            if word in result:
                return word
    except Exception as exc:
        log.warning("Release type classification failed: %s", exc)
    return "minor"


def generate_release_content(
    summary_text: str,
    version_string: str,
    release_type: str,
    codename: str | None,
    llm_model: LlmModel,
    user_id: int = None,
) -> str:
    """Generate formatted HTML release notes via AI."""
    system = (
        "You are a technical writer creating release notes for a SaaS platform. "
        "Write in a professional but friendly tone. "
        "Format as clean HTML (no <html>/<body> tags — content fragments only). "
        "Use: <h3> for section headers, <ul>/<li> for feature lists, "
        "<p> for paragraphs, <strong> for emphasis, "
        "<span class='badge-new'> for NEW labels, "
        "<span class='badge-fix'> for FIX labels, "
        "<span class='badge-improved'> for IMPROVED labels."
    )
    codename_part = f"— {codename}" if codename else ""
    user_prompt = (
        f"Generate release notes for version {version_string} {codename_part}\n"
        f"Release type: {release_type}\n\n"
        f"Based on this technical summary of changes:\n{summary_text}\n\n"
        "Structure as:\n"
        "1. Opening paragraph (1-2 sentences) — what this release focuses on\n"
        "2. What's New section (if major/minor) — bullet list of new features\n"
        "3. Improvements section (if applicable) — bullet list of enhancements\n"
        "4. Bug Fixes section (if patch/any fixes) — bullet list of fixes\n"
        "5. Closing note (1 sentence)\n\n"
        "Use <span class='badge-new'>NEW</span> before new feature bullets,\n"
        "<span class='badge-improved'>IMPROVED</span> before improvements,\n"
        "<span class='badge-fix'>FIX</span> before bug fix bullets.\n\n"
        "Write for non-technical users — plain English, max 400 words."
    )
    return _call_llm(system, user_prompt, llm_model,
                     max_tokens=1500, user_id=user_id)


# ── Main entry point ──────────────────────────────────────────────

def create_release(
    summary_text: str,
    created_by_user_id: int,
    release_type_override: str | None = None,
) -> ReleaseNote:
    """
    Full pipeline: classify → version → codename → generate HTML → save as published.
    If release_type_override is 'patch', 'minor', or 'major', skip AI classification.
    Returns the saved ReleaseNote.
    """
    # Delete any leftover draft releases
    stale_drafts = ReleaseNote.query.filter_by(status="draft").all()
    for d in stale_drafts:
        db.session.delete(d)
    if stale_drafts:
        db.session.flush()

    # Get default or first active chat model for the active tenant
    from .tenant_context import get_active_tenant_id
    tenant_id = get_active_tenant_id()
    model = (
        LlmModel.query.filter_by(tenant_id=tenant_id, is_default=True, is_active=True).first()
        or LlmModel.query.filter_by(tenant_id=tenant_id, is_active=True, model_type="chat").first()
        or LlmModel.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    )
    if not model:
        raise RuntimeError("No active AI model configured. Add one in System Config → Models.")

    # Determine release type
    if release_type_override in ("patch", "minor", "major"):
        release_type = release_type_override
    else:
        release_type = determine_release_type(summary_text, model,
                                              user_id=created_by_user_id)

    major, minor, patch = calculate_next_version(release_type)
    version_string = f"{major}.{minor}.{patch}"
    codename = get_next_codename() if release_type == "major" else None

    content_html = generate_release_content(
        summary_text, version_string, release_type, codename, model,
        user_id=created_by_user_id,
    )

    note = ReleaseNote(
        version_major=major,
        version_minor=minor,
        version_patch=patch,
        version_string=version_string,
        release_type=release_type,
        codename=codename,
        raw_summary=summary_text,
        content_html=content_html,
        status="published",
        published_at=datetime.utcnow(),
        created_by_user_id=created_by_user_id,
    )
    db.session.add(note)
    db.session.commit()

    user = db.session.get(User, created_by_user_id)
    if user:
        log_activity(user=user, action="release_notes.generated",
                     page="Release Notes")
    return note
