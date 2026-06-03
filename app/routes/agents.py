import time
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
from ..models import AgentConversation, AgentMessage, AiAgent, ApiRequestLog, Integration, User

agents_bp = Blueprint("agents", __name__, url_prefix="/agents")

_SKUNK_TIMEOUT = 30  # seconds
_DOCS_PER_PAGE = 25
_ALLOWED_ATTACH_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "pdf", "docx", "txt", "md", "csv"}
_MAX_ATTACH_BYTES = 20 * 1024 * 1024  # 20 MB


def _upload_attachment_to_skunkbox(integration, file_storage) -> dict:
    """Upload a werkzeug FileStorage object to skunkBOX POST /api/v1/attachments.

    Returns the parsed JSON response dict on success.
    Raises ValueError for validation errors (bad extension, too large).
    Raises requests.HTTPError for API errors.
    """
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_ATTACH_EXTENSIONS:
        raise ValueError(f"File type .{ext} is not allowed.")

    file_bytes = file_storage.read()
    if len(file_bytes) > _MAX_ATTACH_BYTES:
        raise ValueError("File exceeds the 20 MB limit.")

    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")]
    api_key = decrypt_value(integration.api_key_encrypted or "")

    resp = http_requests.post(
        f"{base_url}/api/v1/attachments",
        files={"file": (filename, file_bytes, file_storage.content_type or "application/octet-stream")},
        headers={"X-API-Key": api_key},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def _get_docs_integration():
    """Return the first active Documents integration, or None."""
    return Integration.query.filter_by(use_case="Documents", is_active=True).first()


def _log_api(integration, endpoint: str, method: str,
             status_code: int = None, latency_ms: int = None,
             error_message: str = None) -> None:
    """Write one row to ApiRequestLog. Never raises."""
    try:
        db.session.add(ApiRequestLog(
            integration_id=integration.id,
            integration_name=integration.name,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            latency_ms=latency_ms,
            error_message=error_message,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()


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

    url = f"{base_url}/api/v1/{path}"
    t0 = time.monotonic()
    try:
        resp = http_requests.get(
            url,
            params=params or {},
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            timeout=_SKUNK_TIMEOUT,
        )
        latency = int((time.monotonic() - t0) * 1000)
        _log_api(integration, url, "GET", resp.status_code, latency,
                 None if resp.ok else resp.text[:500])
        resp.raise_for_status()
        return resp.json()
    except http_requests.HTTPError:
        raise
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        _log_api(integration, url, "GET", None, latency, str(exc)[:500])
        raise


def _call_skunkbox(integration, skunkbox_agent_id: int,
                   message: str, session_id: str,
                   user_full_name: str = "", username: str = "",
                   attachment_ids: list = None) -> dict:
    """POST to skunkBOX /api/v1/chat/messages. Returns the JSON body or raises."""
    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")]
    if not base_url:
        raise ValueError("Integration has no base URL configured.")

    api_key = decrypt_value(integration.api_key_encrypted or "")
    if not api_key:
        raise ValueError("Integration has no API key configured.")

    payload = {
        "persona_id":     skunkbox_agent_id,
        "session_id":     session_id,
        "user_full_name": user_full_name,
        "username":       username,
        "message":        message,
    }
    if attachment_ids:
        payload["attachment_ids"] = attachment_ids

    url = f"{base_url}/api/v1/chat/messages"
    t0 = time.monotonic()
    try:
        resp = http_requests.post(
            url,
            json=payload,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=_SKUNK_TIMEOUT,
        )
        latency = int((time.monotonic() - t0) * 1000)
        _log_api(integration, url, "POST", resp.status_code, latency,
                 None if resp.ok else resp.text[:500])
        resp.raise_for_status()
        return resp.json()
    except http_requests.HTTPError:
        raise
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        _log_api(integration, url, "POST", None, latency, str(exc)[:500])
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Conversations list
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/")
@login_required
@permission_required("conversations", "view")
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

    tab = request.args.get("tab", "mine")  # mine | all | favorites

    f_agent_ids = request.args.getlist("agent_ids", type=int)
    f_user_ids  = request.args.getlist("user_ids", type=int)
    f_date_from = request.args.get("date_from", "").strip()
    f_date_to   = request.args.get("date_to", "").strip()

    from datetime import datetime as _dt

    def _apply_date_filters(q):
        if f_date_from:
            q = q.filter(AgentConversation.updated_at >= f_date_from)
        if f_date_to:
            try:
                end_dt = _dt.strptime(f_date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                q = q.filter(AgentConversation.updated_at <= end_dt)
            except ValueError:
                pass
        return q

    conv_q = (
        AgentConversation.query
        .join(AiAgent, AiAgent.id == AgentConversation.ai_agent_id)
        .filter(AgentConversation.is_archived == False, AiAgent.is_active == True)
    )
    if tab == "all":
        if f_agent_ids:
            conv_q = conv_q.filter(AgentConversation.ai_agent_id.in_(f_agent_ids))
        if f_user_ids:
            conv_q = conv_q.filter(AgentConversation.user_id.in_(f_user_ids))
        conv_q = _apply_date_filters(conv_q)
    elif tab == "favorites":
        conv_q = conv_q.filter(
            AgentConversation.user_id == current_user.id,
            AgentConversation.is_favorite == True,
        )
        if f_agent_ids:
            conv_q = conv_q.filter(AgentConversation.ai_agent_id.in_(f_agent_ids))
        conv_q = _apply_date_filters(conv_q)
    else:  # mine (default)
        conv_q = conv_q.filter(AgentConversation.user_id == current_user.id)
    conversations = conv_q.order_by(AgentConversation.updated_at.desc()).all()

    all_users = (
        User.query.filter_by(is_active=True)
        .order_by(User.first_name, User.last_name, User.username)
        .all()
    )

    return render_template(
        "agents/list.html",
        ai_agents=ai_agents,
        conversations=conversations,
        tab=tab,
        all_users=all_users,
        f_agent_ids=f_agent_ids,
        f_user_ids=f_user_ids,
        f_date_from=f_date_from,
        f_date_to=f_date_to,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Conversations", "url": url_for("agents.list_conversations")},
            {"label": "Favorites" if tab == "favorites" else "All Conversations" if tab == "all" else "My Conversations", "url": None},
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Start a new conversation
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/new", methods=["POST"])
@login_required
@permission_required("conversations", "view")
def new_conversation():
    agent_id = request.form.get("agent_id", "").strip()
    if not agent_id:
        flash("Please select an agent.", "error")
        return redirect(url_for("agents.list_conversations"))

    agent = db.session.get(AiAgent, int(agent_id))
    if not agent or not agent.is_active:
        abort(404)

    initial_message = request.form.get("initial_message", "").strip()

    conv = AgentConversation(
        ai_agent_id=agent.id,
        user_id=current_user.id,
        title=initial_message[:80] if initial_message else f"Conversation with {agent.name}",
        skunkbox_session_id=str(uuid.uuid4()),
    )
    db.session.add(conv)
    db.session.commit()
    log_activity(current_user, "conversation.started", page="AI Agents")

    kwargs = {"conversation_id": conv.id}
    if initial_message:
        kwargs["q"] = initial_message
    redirect_url = url_for("agents.view_conversation", **kwargs)

    # AJAX callers (New Conversation modal) get JSON so they can upload
    # attachments to the new conv before navigating.
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "conv_id": conv.id, "redirect_url": redirect_url})

    return redirect(redirect_url)


# ─────────────────────────────────────────────────────────────────────────────
# View / chat in a conversation
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/<int:conversation_id>")
@login_required
@permission_required("conversations", "view")
def view_conversation(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id and not current_user.is_admin():
        abort(403)

    raw_messages = conv.messages.order_by(AgentMessage.created_at).all()

    from ..models import MessageAttachment
    message_ids = [m.id for m in raw_messages]
    attachments_by_message_id = {}
    if message_ids:
        att_records = MessageAttachment.query.filter(
            MessageAttachment.message_id.in_(message_ids)
        ).all()
        for att in att_records:
            attachments_by_message_id.setdefault(att.message_id, []).append(att)

    messages_data = [
        {
            "id":          m.id,
            "role":        m.role,
            "content":     m.content,
            "rag_sources": m.rag_sources_list,
            "created_at":  m.created_at.isoformat(),
            "attachments": [
                {
                    "id":       a.skunkbox_attachment_id,
                    "filename": a.original_filename,
                    "category": a.file_category,
                    "mime_type": a.mime_type,
                }
                for a in attachments_by_message_id.get(m.id, [])
            ],
        }
        for m in raw_messages
    ]
    return render_template(
        "agents/conversation.html",
        conv=conv,
        agent=conv.agent,
        messages=raw_messages,
        messages_data=messages_data,
        attachments_by_message_id=attachments_by_message_id,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Conversations", "url": url_for("agents.list_conversations")},
            {"label": conv.title or conv.agent.name, "url": None},
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Send a message  (AJAX — returns JSON)
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/<int:conversation_id>/send", methods=["POST"])
@login_required
@permission_required("conversations", "view")
def send_message(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id and not current_user.is_admin():
        return jsonify({"ok": False, "error": "Forbidden"}), 403

    data = request.get_json(force=True) or {}
    content = (data.get("message") or "").strip()

    raw_att_ids     = data.get("attachment_ids") or []
    attachment_ids  = [int(x) for x in raw_att_ids if str(x).isdigit()][:5]
    attachment_meta = data.get("attachment_metadata") or []  # list of dicts from frontend

    # Must have text OR at least one attachment
    if not content and not attachment_ids:
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

    # Auto-title: use text, or first attachment filename, or fallback
    if not conv.title or conv.title == f"Conversation with {agent.name}":
        if content:
            conv.title = content[:80]
        elif attachment_meta:
            conv.title = attachment_meta[0].get("original_filename", "File attached")[:80]
        else:
            conv.title = "File attached"

    db.session.commit()

    # Call skunkBOX — use placeholder when user sent attachment-only (no text)
    skunkbox_message = content or "[File attached — please review]"
    try:
        result = _call_skunkbox(
            integration=agent.integration,
            skunkbox_agent_id=agent.skunkbox_agent_id,
            message=skunkbox_message,
            session_id=conv.skunkbox_session_id,
            user_full_name=current_user.display_name or current_user.username,
            username=current_user.username,
            attachment_ids=attachment_ids,
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

    # Save local MessageAttachment records using metadata sent by the frontend
    from ..models import MessageAttachment as MsgAtt
    for meta in attachment_meta:
        try:
            db.session.add(MsgAtt(
                message_id             = user_msg.id,
                skunkbox_attachment_id = int(meta["attachment_id"]),
                original_filename      = meta["original_filename"],
                mime_type              = meta["mime_type"],
                file_category          = meta["file_category"],
                file_size_bytes        = meta.get("file_size_bytes"),
            ))
        except (KeyError, ValueError):
            pass  # skip malformed entries
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
# Attachment upload proxy
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/<int:conversation_id>/attachments", methods=["POST"])
@login_required
@permission_required("conversations", "view")
def upload_attachment(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id and not current_user.is_admin():
        return jsonify({"ok": False, "error": "Forbidden"}), 403

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "No file provided."}), 400

    agent = conv.agent
    if not agent or not agent.is_active:
        return jsonify({"ok": False, "error": "Agent not available."}), 400

    try:
        result = _upload_attachment_to_skunkbox(agent.integration, file)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Upload failed: {e}"}), 502

    return jsonify({
        "ok": True,
        "attachment_id":     result["attachment_id"],
        "original_filename": result["original_filename"],
        "file_category":     result["file_category"],
        "mime_type":         result["mime_type"],
        "file_size_bytes":   result.get("file_size_bytes"),
    })


@agents_bp.route("/attachments/<int:skunkbox_attachment_id>/download")
@login_required
@permission_required("conversations", "view")
def download_attachment(skunkbox_attachment_id):
    """Proxy a file download from skunkBOX.
    Security: verify the current user owns a conversation containing this attachment.
    """
    from ..models import MessageAttachment

    att_record = (
        MessageAttachment.query
        .join(AgentMessage, AgentMessage.id == MessageAttachment.message_id)
        .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
        .filter(
            MessageAttachment.skunkbox_attachment_id == skunkbox_attachment_id,
            AgentConversation.user_id == current_user.id,
        )
        .first()
    )
    if not att_record:
        abort(404)

    msg  = db.session.get(AgentMessage, att_record.message_id)
    conv = db.session.get(AgentConversation, msg.conversation_id)
    integration = conv.agent.integration

    base_url = (integration.base_url or "").rstrip("/")
    if base_url.endswith("/api/v1"):
        base_url = base_url[:-len("/api/v1")]
    api_key = decrypt_value(integration.api_key_encrypted or "")

    try:
        resp = http_requests.get(
            f"{base_url}/api/v1/attachments/{skunkbox_attachment_id}",
            headers={"X-API-Key": api_key},
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()
        content_disposition = f'attachment; filename="{att_record.original_filename}"'
        return Response(
            stream_with_context(resp.iter_content(chunk_size=8192)),
            content_type=resp.headers.get("Content-Type", "application/octet-stream"),
            headers={"Content-Disposition": content_disposition},
        )
    except Exception:
        abort(404)


# ─────────────────────────────────────────────────────────────────────────────
# Archive a conversation
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Learning Center — document list + detail (reads from Documents integration)
# ─────────────────────────────────────────────────────────────────────────────

@agents_bp.route("/learning-center")
@login_required
@permission_required("learning_center", "view")
def learning_center():
    page       = request.args.get("page", 1, type=int)
    active_tab = request.args.get("tab", "all")   # "all" or str(collection_id)
    integration = _get_docs_integration()
    docs, total, total_pages, error = [], 0, 1, None
    collections = []   # [{id, name}] sorted A-Z

    if integration:
        try:
            # ── Single API call: fetch the full corpus (≤500 docs) ─────────
            # Filtering and pagination are done in Python to avoid a second
            # round-trip and stay well within the 10 RPM rate limit.
            all_data = _call_skunkbox_get(integration, "documents", {
                "limit": 500, "offset": 0,
            })
            all_docs = (all_data.get("documents") or all_data.get("items")
                        or all_data.get("data")
                        or (all_data if isinstance(all_data, list) else []))

            # Build sorted collections list from the corpus
            seen: dict = {}
            for d in all_docs:
                for c in (d.get("collections") or []):
                    seen[c["id"]] = c["name"]
            collections = sorted(
                [{"id": cid, "name": name} for cid, name in seen.items()],
                key=lambda c: c["name"].lower(),
            )

            # Filter by collection when a collection tab is active
            if active_tab != "all":
                try:
                    coll_id = int(active_tab)
                    all_docs = [
                        d for d in all_docs
                        if any(c["id"] == coll_id for c in (d.get("collections") or []))
                    ]
                except ValueError:
                    active_tab = "all"

            # Paginate in Python
            total = len(all_docs)
            total_pages = max(1, (total + _DOCS_PER_PAGE - 1) // _DOCS_PER_PAGE)
            page = min(page, total_pages)
            start = (page - 1) * _DOCS_PER_PAGE
            docs = all_docs[start: start + _DOCS_PER_PAGE]

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
        collections=collections,
        active_tab=active_tab,
        breadcrumbs=[
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Learning Center", "url": url_for("agents.learning_center")},
            {"label": next((c["name"] for c in collections if str(c["id"]) == active_tab), "All Documents"), "url": None},
        ],
    )


@agents_bp.route("/learning-center/<doc_id>")
@login_required
@permission_required("learning_center", "view")
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
            {"label": "Home", "url": url_for("agents.list_conversations")},
            {"label": "Learning Center", "url": url_for("agents.learning_center")},
            {"label": title, "url": None},
        ],
    )


@agents_bp.route("/learning-center/<doc_id>/file")
@login_required
@permission_required("learning_center", "view")
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


@agents_bp.route("/<int:conversation_id>/favorite", methods=["POST"])
@login_required
@permission_required("conversations", "view")
def toggle_favorite(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id and not current_user.is_admin():
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    conv.is_favorite = not conv.is_favorite
    db.session.commit()
    return jsonify({"ok": True, "is_favorite": conv.is_favorite})


@agents_bp.route("/<int:conversation_id>/archive", methods=["POST"])
@login_required
@permission_required("conversations", "view")
def archive_conversation(conversation_id):
    conv = db.get_or_404(AgentConversation, conversation_id)
    if conv.user_id != current_user.id and not current_user.is_admin():
        abort(403)
    conv.is_archived = True
    db.session.commit()
    log_activity(current_user, "conversation.archived", page="AI Agents")
    flash("Conversation archived.", "success")
    return redirect(url_for("agents.list_conversations"))
