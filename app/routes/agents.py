import uuid
import requests as http_requests
from flask import (Blueprint, Response, abort, flash, jsonify, redirect,
                   render_template, request, stream_with_context, url_for)
from flask_login import current_user, login_required

from ..access import permission_required
from ..activity_logger import log_activity
from ..crypto import decrypt_value
from ..extensions import db
from sqlalchemy import func
from ..models import AgentConversation, AgentMessage, AiAgent, Integration

agents_bp = Blueprint("agents", __name__, url_prefix="/agents")

_SKUNK_TIMEOUT = 30  # seconds
_DOCS_PER_PAGE = 25


def _get_docs_integration():
    """Return the first active Documents integration, or None."""
    return Integration.query.filter_by(use_case="Documents", is_active=True).first()


def _call_skunkbox_get(integration, path: str, params: dict = None) -> dict:
    """Generic GET to skunkBOX API. Returns JSON or raises."""
    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[: -len("/api/v1")]
    if not base_url:
        raise ValueError("Integration has no base URL configured.")
    api_key = decrypt_value(integration.api_key_encrypted or "")
    if not api_key:
        raise ValueError("Integration has no API key configured.")
    resp = http_requests.get(
        f"{base_url}/api/v1/{path}",
        params=params or {},
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        timeout=_SKUNK_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _call_skunkbox(integration, skunkbox_agent_id: int,
                   message: str, session_id: str,
                   user_full_name: str = "", username: str = "") -> dict:
    """POST to skunkBOX /api/v1/chat/messages. Returns the JSON body or raises."""
    base_url = (integration.base_url or "").rstrip("/")
    # Normalise: strip trailing /api/v1 so the path below never doubles it
    if base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")]
    if not base_url:
        raise ValueError("Integration has no base URL configured.")

    api_key = decrypt_value(integration.api_key_encrypted or "")
    if not api_key:
        raise ValueError("Integration has no API key configured.")

    payload = {
        "persona_id": skunkbox_agent_id,
        "session_id": session_id,
        "user_full_name": user_full_name,
        "username": username,
        "message": message,
    }

    resp = http_requests.post(
        f"{base_url}/api/v1/chat/messages",
        json=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=_SKUNK_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Conversations list
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/")
@login_required
@permission_required("agents", "view")
def list_conversations():
    # ── Auto-delete empty conversations (no messages sent) ──────────────────
    has_msg_subq = db.session.query(AgentMessage.conversation_id).distinct()
    (AgentConversation.query
     .filter(
         AgentConversation.user_id == current_user.id,
         AgentConversation.id.notin_(has_msg_subq),
     )
     .delete(synchronize_session="fetch"))
    db.session.commit()

    # ── Active agents ordered by most recently used by this user ────────────
    ai_agents = AiAgent.query.filter_by(is_active=True).order_by(AiAgent.name).all()
    last_used = dict(
        db.session.query(
            AgentConversation.ai_agent_id,
            func.max(AgentConversation.updated_at),
        )
        .filter_by(user_id=current_user.id)
        .group_by(AgentConversation.ai_agent_id)
        .all()
    )
    ai_agents.sort(key=lambda a: (
        last_used.get(a.id) is None,          # used agents first
        -(last_used[a.id].timestamp() if last_used.get(a.id) else 0),
        a.name.lower(),                        # then alpha
    ))

    view_all = request.args.get("view") == "all"

    conv_q = AgentConversation.query.filter_by(is_archived=False)
    if not view_all:
        conv_q = conv_q.filter_by(user_id=current_user.id)
    conversations = conv_q.order_by(AgentConversation.updated_at.desc()).all()

    return render_template(
        "agents/list.html",
        ai_agents=ai_agents,
        conversations=conversations,
        view_all=view_all,
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "AI Agents", "url": url_for("agents.list_conversations")},
            {"label": "Conversations", "url": None},
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Start a new conversation
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/new", methods=["POST"])
@login_required
@permission_required("agents", "view")
def new_conversation():
    agent_id = request.form.get("agent_id", "").strip()
    if not agent_id:
        flash("Please select an agent.", "error")
        return redirect(url_for("agents.list_conversations"))

    agent = db.session.get(AiAgent, int(agent_id))
    if not agent or not agent.is_active:
        abort(404)

    conv = AgentConversation(
        ai_agent_id=agent.id,
        user_id=current_user.id,
        title=f"Conversation with {agent.name}",
        skunkbox_session_id=str(uuid.uuid4()),
    )
    db.session.add(conv)
    db.session.commit()
    log_activity(current_user, "conversation.started", page="AI Agents")
    return redirect(url_for("agents.view_conversation", conversation_id=conv.id))


# ─────────────────────────────────────────────────────────────────────────────
# View / chat in a conversation
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/<int:conversation_id>")
@login_required
@permission_required("agents", "view")
def view_conversation(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id:
        abort(403)

    raw_messages = conv.messages.order_by(AgentMessage.created_at).all()
    messages_data = [
        {
            "id":          m.id,
            "role":        m.role,
            "content":     m.content,
            "rag_sources": m.rag_sources_list,
            "created_at":  m.created_at.isoformat(),
        }
        for m in raw_messages
    ]
    return render_template(
        "agents/conversation.html",
        conv=conv,
        agent=conv.agent,
        messages=raw_messages,
        messages_data=messages_data,
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "AI Agents", "url": url_for("agents.list_conversations")},
            {"label": "Conversations", "url": url_for("agents.list_conversations")},
            {"label": conv.title or conv.agent.name, "url": None},
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Send a message  (AJAX — returns JSON)
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/<int:conversation_id>/send", methods=["POST"])
@login_required
@permission_required("agents", "view")
def send_message(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id:
        return jsonify({"ok": False, "error": "Forbidden"}), 403

    data = request.get_json(force=True) or {}
    content = (data.get("message") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Message is empty."}), 400

    agent = conv.agent
    if not agent or not agent.is_active:
        return jsonify({"ok": False, "error": "Agent is not available."}), 400

    # Persist the user message immediately
    user_msg = AgentMessage(
        conversation_id=conv.id,
        role="user",
        content=content,
    )
    db.session.add(user_msg)

    # Auto-title the conversation from the first user message
    if not conv.title or conv.title == f"Conversation with {agent.name}":
        conv.title = content[:80]

    db.session.commit()

    # Call skunkBOX
    try:
        result = _call_skunkbox(
            integration=agent.integration,
            skunkbox_agent_id=agent.skunkbox_agent_id,
            message=content,
            session_id=conv.skunkbox_session_id,
            user_full_name=current_user.display_name or current_user.username,
            username=current_user.username,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502

    # Persist session_id for continuity (skunkBOX returns it)
    new_session_id = result.get("session_id") or result.get("sessionId")
    if new_session_id and new_session_id != conv.skunkbox_session_id:
        conv.skunkbox_session_id = str(new_session_id)

    # Extract the assistant reply
    reply_text = (
        result.get("response")
        or result.get("message")
        or result.get("content")
        or result.get("text")
        or "[No response]"
    )

    # Extract RAG sources if the API returned them
    import json as _json
    raw_sources = result.get("rag_sources") or []
    rag_sources_json = _json.dumps(raw_sources) if raw_sources else None

    assistant_msg = AgentMessage(
        conversation_id=conv.id,
        role="assistant",
        content=reply_text,
        rag_sources=rag_sources_json,
    )
    db.session.add(assistant_msg)
    db.session.commit()

    return jsonify({
        "ok": True,
        "user_message_id": user_msg.id,
        "assistant": {
            "id": assistant_msg.id,
            "content": reply_text,
            "created_at": assistant_msg.created_at.isoformat(),
            "rag_sources": raw_sources,
        },
    })


# ─────────────────────────────────────────────────────────────────────────────
# Archive a conversation
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Learning Center — document list + detail (reads from Documents integration)
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/learning-center")
@login_required
@permission_required("agents", "view")
def learning_center():
    page = request.args.get("page", 1, type=int)
    integration = _get_docs_integration()
    docs, total, total_pages, error = [], 0, 1, None

    if integration:
        try:
            data = _call_skunkbox_get(integration, "documents", {
                "page": page,
                "per_page": _DOCS_PER_PAGE,
            })
            # Defensive: handle {documents:[...]}, {items:[...]}, {data:[...]}, or bare list
            docs = (data.get("documents")
                    or data.get("items")
                    or data.get("data")
                    or (data if isinstance(data, list) else []))
            total = int(data.get("total") or data.get("count")
                        or data.get("total_count") or len(docs))
            total_pages = int(
                data.get("pages") or data.get("total_pages")
                or max(1, (total + _DOCS_PER_PAGE - 1) // _DOCS_PER_PAGE)
            )
        except Exception as exc:
            error = str(exc)

    return render_template(
        "agents/learning_center.html",
        docs=docs,
        page=page,
        per_page=_DOCS_PER_PAGE,
        total=total,
        total_pages=total_pages,
        integration=integration,
        error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "AI Agents", "url": url_for("agents.list_conversations")},
            {"label": "Learning Center", "url": None},
        ],
    )


@agents_bp.route("/learning-center/<doc_id>")
@login_required
@permission_required("agents", "view")
def learning_center_doc(doc_id):
    integration = _get_docs_integration()
    doc, error = None, None

    if integration:
        try:
            data = _call_skunkbox_get(integration, f"documents/{doc_id}")
            # Unwrap {document: {...}} wrapper if present
            doc = data.get("document") or (data if isinstance(data, dict) else None)
        except Exception as exc:
            error = str(exc)

    title = (doc.get("title") or doc.get("name") or doc.get("filename")
             or f"Document {doc_id}") if doc else f"Document {doc_id}"
    return render_template(
        "agents/learning_center_detail.html",
        doc=doc,
        doc_id=doc_id,
        integration=integration,
        error=error,
        breadcrumbs=[
            {"label": "Home", "url": url_for("main.dashboard")},
            {"label": "AI Agents", "url": url_for("agents.list_conversations")},
            {"label": "Learning Center", "url": url_for("agents.learning_center")},
            {"label": title, "url": None},
        ],
    )


@agents_bp.route("/learning-center/<doc_id>/file")
@login_required
@permission_required("agents", "view")
def learning_center_file(doc_id):
    """Proxy the raw file from skunkBOX so the browser can display it inline.
    Tries several common download URL patterns in order."""
    integration = _get_docs_integration()
    if not integration:
        return _proxy_error("No Documents integration configured.")
    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[: -len("/api/v1")]
    api_key = decrypt_value(integration.api_key_encrypted or "")
    if not api_key:
        return _proxy_error("Integration has no API key configured.")

    # Try common skunkBOX download endpoint patterns in order
    version = request.args.get("version", "1")
    candidates = [
        f"{base_url}/api/v1/documents/{doc_id}/download",
        f"{base_url}/api/v1/documents/{doc_id}/versions/{version}/download",
        f"{base_url}/api/v1/documents/{doc_id}/file",
        f"{base_url}/api/v1/documents/{doc_id}/content",
    ]
    headers = {"X-API-Key": api_key}
    last_err = "All download endpoints returned errors."
    for url in candidates:
        try:
            resp = http_requests.get(url, headers=headers, timeout=60, stream=True)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "application/pdf")
                # Force inline display — never let the API's attachment header trigger a download
                return Response(
                    stream_with_context(resp.iter_content(chunk_size=8192)),
                    content_type=content_type,
                    headers={"Content-Disposition": "inline"},
                )
            last_err = f"{url} → HTTP {resp.status_code}"
        except Exception as exc:
            last_err = f"{url} → {exc}"

    return _proxy_error(last_err)


def _proxy_error(message: str):
    """Return a minimal HTML page that displays an error inside the preview iframe."""
    html = f"""<!DOCTYPE html><html><body style="margin:40px;font-family:sans-serif;color:#666">
    <p style="font-size:14px">⚠ Could not load preview: {message}</p>
    </body></html>"""
    return Response(html, status=502, content_type="text/html")


@agents_bp.route("/<int:conversation_id>/archive", methods=["POST"])
@login_required
@permission_required("agents", "view")
def archive_conversation(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id:
        abort(403)
    conv.is_archived = True
    db.session.commit()
    log_activity(current_user, "conversation.archived", page="AI Agents")
    flash("Conversation archived.", "success")
    return redirect(url_for("agents.list_conversations"))
